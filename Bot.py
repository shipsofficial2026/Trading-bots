cat > Bot.py << 'EOF'
import ccxt, time, requests, json, os, pandas as pd, mplfinance as mpf, logging
from datetime import datetime, date
from dotenv import load_dotenv
load_dotenv()

# ====================== V9.9.9 FINAL - 24/7 QWEN2.5 BOSS - DEMO ======================
IS_LIVE = True # ← FALSE = DEMO. True = REAL MONEY. Mag-ingat.

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GROQ_KEY_1 = os.getenv('GROQ_KEY_1')
GROQ_KEY_2 = os.getenv('GROQ_KEY_2') 
DEEPSEEK_KEY = os.getenv('DEEPSEEK_KEY')
GEMINI_KEY = os.getenv('GEMINI_KEY')
BINANCE_API = os.getenv('BINANCE_API')
BINANCE_SECRET = os.getenv('BINANCE_SECRET')

CAPITAL = 1000.0
BASE_TRADE_SIZE = 200
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'TON/USDT', 'ADA/USDT']

SL_PCT = 0.05
TP1_PCT = 0.10
TP2_PCT = 0.15
HARD_STOP_PCT = 0.07
MIN_CONFIDENCE = 78
MAX_OPEN = 4
MAX_DAILY_LOSS_PCT = 0.10
FEE_RATE = 0.0005
CD_MINS_AFTER_2LOSS = 60

MODELS = {
    "BOSS":   ["groq", "qwen2.5-72b", GROQ_KEY_1],
    "SCANNER":["groq", "llama-3.1-8b-instant", GROQ_KEY_2],
    "HUNTER": ["deepseek", "deepseek-chat", DEEPSEEK_KEY],
    "ELDER":  ["gemini", "gemini-1.5-flash-latest", GEMINI_KEY]
}

PROMPTS = {
    "BOSS": """You are an elite 24/7 crypto trader using Qwen2.5-72B. 
Analyze this 30m chart of {symbol}. 
Decide if it's a strong LONG setup.
Rules: Price > EMA200, EMA50 > EMA200, healthy volume.
Be strict but decisive. 
Return ONLY valid JSON:
{{"vote":"BUY","confidence":85,"reason":"short reason"}}""",
    "SCANNER": "Pick the SINGLE strongest long setup right now: {symbols}. Return ONLY: {{\"pick\":\"BTC/USDT\"}}",
    "HUNTER": "Valid long setup on {symbol} 30m? Return ONLY: {{\"valid\":true}}",
    "ELDER": "Safe to LONG {symbol} now in 24/7 mode? Return ONLY: {{\"approve\":true}}"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s',
                    handlers=[logging.FileHandler("bot_v9.9.9.log"), logging.StreamHandler()])

exchange = ccxt.binancedm({ # DEMO TRADING NA TO BOSS
    'apiKey': BINANCE_API,
    'secret': BINANCE_SECRET,
    'options': {'defaultType': 'future'},
    'enableRateLimit': True
})
# Tinanggal na set_sandbox_mode kasi deprecated na

# ====================== STATE ======================
daily_stats = {'wins': 0, 'losses': 0, 'pnl': 0.0, 'trades': 0}
active_trades = {}
last_results = []
cd_until = 0
trades_today = 0
daily_pnl = 0.0
last_reset_date = date.today()

# ====================== HELPERS ======================
def tg(msg: str, photo=None):
    try:
        if photo and os.path.exists(photo):
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                          data={'chat_id': TELEGRAM_CHAT_ID, 'caption': msg},
                          files={'photo': open(photo, 'rb')})
        else:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg})
    except Exception as e: 
        logging.error(f"TG Error: {e}")

def normalize_symbol(s):
    return s.replace('/', '').replace(':USDT', 'USDT').upper()

def get_leverage(symbol):
    return 15 if "BTC" in symbol else 10

def save_chart(df, symbol):
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[['open','high','low','close','volume']]
    df.columns = ['Open','High','Low','Close','Volume']
    apds = [mpf.make_addplot(df['Close'].ewm(span=50).mean(), color='blue'),
            mpf.make_addplot(df['Close'].ewm(span=200).mean(), color='orange')]
    mpf.plot(df[-100:], type='candle', style='yahoo', addplot=apds,
             title=f'{symbol} 30m', savefig='chart.png', volume=True)
    return 'chart.png'

def safe_json_parse(text):
    text = text.strip().strip('```json').strip('```').strip()
    try: return json.loads(text)
    except:
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try: return json.loads(match.group(0))
            except: pass
        return {}

def ask_ai_vision(bot_name, prompt, image_path=None):
    provider, model, key = MODELS[bot_name]
    if not key: 
        logging.error(f"{bot_name} Key is missing in .env")
        return {}
    try:
        if provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            content = [{"type": "text", "text": prompt}]
            if image_path:
                import base64
                with open(image_path, "rb") as f: b64 = base64.b64encode(f.read()).decode()
                content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
            body = {"model": model, "messages": [{"role":"user","content": content}], "response_format": {"type": "json_object"}}
            r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=40)
        elif provider == "deepseek":
            url = "https://api.deepseek.com/chat/completions"
            body = {"model": model, "messages": [{"role":"user","content":prompt}], "response_format": {"type": "json_object"}}
            r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=40)
        elif provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            body = {"contents":[{"parts":[{"text": prompt}]}],"generationConfig": {"response_mime_type": "application/json"}}
            r = requests.post(url, json=body, timeout=40)
        r.raise_for_status()
        text = r.json()['candidates'][0]['content']['parts'][0]['text'] if provider == "gemini" else r.json()['choices'][0]['message']['content']
        return safe_json_parse(text)
    except Exception as e:
        logging.error(f"{bot_name} failed: {e}")
        return {}

print(f"🤖 V9.9.9 FINAL | 24/7 Qwen2.5-72B BOSS | Live: {IS_LIVE} | DEMO MODE")

while True:
    try:
        if time.time() < cd_until or daily_pnl <= -CAPITAL * MAX_DAILY_LOSS_PCT:
            time.sleep(60)
            continue

        balance = exchange.fetch_balance()['USDT']['free']
        open_positions = [p for p in exchange.fetch_positions() if float(p.get('contracts', 0)) > 0]

        if balance < BASE_TRADE_SIZE or len(open_positions) >= MAX_OPEN:
            time.sleep(40)
            continue

        pick = ask_ai_vision("SCANNER", PROMPTS["SCANNER"].format(symbols=SYMBOLS)).get('pick')
        if not pick or pick in active_trades:
            time.sleep(45)
            continue

        ohlcv = exchange.fetch_ohlcv(pick, '30m', limit=150)
        df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
        chart_path = save_chart(df, pick)

        boss = ask_ai_vision("BOSS", PROMPTS["BOSS"].format(symbol=pick), chart_path)
        hunter = ask_ai_vision("HUNTER", PROMPTS["HUNTER"].format(symbol=pick))
        elder = ask_ai_vision("ELDER", PROMPTS["ELDER"].format(symbol=pick))

        votes = sum(1 for v in [boss.get('vote'), hunter.get('valid'), elder.get('approve')] if v in [True, 'BUY'])
        conf = boss.get('confidence', 0)

        if boss.get('vote') == "BUY" and conf >= MIN_CONFIDENCE and votes >= 2:
            price = df['close'].iloc[-1]
            LEV = get_leverage(pick)
            trade_size = round(min(BASE_TRADE_SIZE * (conf / 100), CAPITAL * 0.25), 2)
            amt = round((trade_size * LEV * 0.999) / price, 4)
            amt_half = round(amt / 2, 4)

            exchange.set_margin_mode('isolated', pick)
            exchange.set_leverage(LEV, pick)
            exchange.create_market_buy_order(pick, amt)

            sl = round(price * (1 - SL_PCT), 2)
            tp1 = round(price * (1 + TP1_PCT), 2)
            tp2 = round(price * (1 + TP2_PCT), 2)
            hard_stop = round(price * (1 - HARD_STOP_PCT), 2)

            sl_order = exchange.create_order(pick, 'STOP_MARKET', 'sell', amt, None, {'stopPrice': sl, 'closeOnTrigger': True, 'reduceOnly': True})
            tp1_order = exchange.create_order(pick, 'TAKE_PROFIT_MARKET', 'sell', amt_half, None, {'stopPrice': tp1, 'closeOnTrigger': True, 'reduceOnly': True})
            tp2_order = exchange.create_order(pick, 'TAKE_PROFIT_MARKET', 'sell', amt_half, None, {'stopPrice': tp2, 'closeOnTrigger': True, 'reduceOnly': True})
            hard_order = exchange.create_order(pick, 'STOP_MARKET', 'sell', amt, None, {'stopPrice': hard_stop, 'closeOnTrigger': True, 'reduceOnly': True})

            active_trades[pick] = {'entry_price': price, 'amt': amt, 'amt_half': amt_half, 'sl_order_id': sl_order['id'], 'tp1_hit': False}
            tg(f"🚀 DEMO ENTRY → {pick} LONG x{LEV} | BOSS {conf}% | Votes: {votes}/4")

        time.sleep(30)
    except Exception as e:
        logging.error(f"Main error: {e}")
        time.sleep(60)
EOF
