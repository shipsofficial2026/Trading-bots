import ccxt, time, requests, json, os, pandas as pd, mplfinance as mpf, logging
from datetime import datetime, date
from dotenv import load_dotenv
load_dotenv()

# ====================== V9.9.9 LIVE - BINANCE REAL ======================
IS_LIVE = True  # ← TRUE = REAL MONEY. DANGER! DOBLE CHECK MO .ENV MO!

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GROQ_KEY_1 = os.getenv('GROQ_KEY_1')
GROQ_KEY_2 = os.getenv('GROQ_KEY_2') 
DEEPSEEK_KEY = os.getenv('DEEPSEEK_KEY')
GEMINI_KEY = os.getenv('GEMINI_KEY')
BINANCE_API = os.getenv('BINANCE_API')
BINANCE_SECRET = os.getenv('BINANCE_SECRET')

CAPITAL = 50.0 # ← $50 lang muna boss pang test. Wag $1000 agad
BASE_TRADE_SIZE = 10 # ← $20 lang per trade
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'TON/USDT', 'ADA/USDT']
MIN_CONFIDENCE = 85 # ← Taasan natin para mas safe
MAX_OPEN = 2 # ← 2 lang muna open trades para di magkalat
SL_PCT = 0.05
TP1_PCT = 0.10
TP2_PCT = 0.15
HARD_STOP_PCT = 0.07

MODELS = {
    "BOSS":   ["groq", "qwen2.5-72b", GROQ_KEY_1],
    "SCANNER":["groq", "llama-3.1-8b-instant", GROQ_KEY_2],
    "HUNTER": ["deepseek", "deepseek-chat", DEEPSEEK_KEY],
    "ELDER":  ["gemini", "gemini-1.5-flash-latest", GEMINI_KEY]
}

PROMPTS = {
    "BOSS": """You are an elite 24/7 crypto trader. Analyze this 30m chart of {symbol}. 
Rules: Price > EMA200, EMA50 > EMA200. Return ONLY JSON: {{"vote":"BUY","confidence":85,"reason":"short"}}""",
    "SCANNER": "Pick the SINGLE strongest long: {symbols}. Return ONLY: {{\"pick\":\"BTC/USDT\"}}",
    "HUNTER": "Valid long on {symbol} 30m? Return ONLY: {{\"valid\":true}}",
    "ELDER": "Safe to LONG {symbol}? Return ONLY: {{\"approve\":true}}"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s',
                    handlers=[logging.FileHandler("bot_v9.9.9_live.log"), logging.StreamHandler()])

# ========= LIVE MODE FOR FUTURES =========
exchange = ccxt.binanceusdm({
    'apiKey': BINANCE_API,
    'secret': BINANCE_SECRET,
    'options': {'defaultType': 'future'},
    'enableRateLimit': True
})
exchange.enable_demo_trading(False) # <--- FALSE = LIVE NA TO

active_trades = {}

def tg(msg: str, photo=None):
    try:
        if photo and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            if photo and os.path.exists(photo):
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                              data={'chat_id': TELEGRAM_CHAT_ID, 'caption': msg},
                              files={'photo': open(photo, 'rb')}, timeout=10)
            else:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                              data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg}, timeout=10)
    except Exception as e: 
        logging.error(f"TG Error: {e}")

def get_leverage(symbol):
    return 10 if "BTC" in symbol else 8 # ← Binaba ko leverage boss para mas safe

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
    except: return {}

def ask_ai(bot_name, prompt, image_path=None):
    provider, model, key = MODELS[bot_name]
    if not key: 
        logging.error(f"{bot_name} Key missing")
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
            r = requests.post("https://api.deepseek.com/chat/completions", headers={"Authorization": f"Bearer {key}"}, json={"model": model, "messages": [{"role":"user","content":prompt}], "response_format": {"type": "json_object"}}, timeout=40)
        elif provider == "gemini":
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}", json={"contents":[{"parts":[{"text": prompt}]}],"generationConfig": {"response_mime_type": "application/json"}}, timeout=40)
        r.raise_for_status()
        text = r.json()['candidates'][0]['content']['parts'][0]['text'] if provider == "gemini" else r.json()['choices'][0]['message']['content']
        return safe_json_parse(text)
    except Exception as e:
        logging.error(f"{bot_name} failed: {e}")
        return {}

logging.info(f"🤖 V9.9.9 LIVE | AI BOSS TEAM | REAL TRADING MODE | Live: {IS_LIVE}")

while True:
    try:
        balance = exchange.fetch_balance()['USDT']['free']
        open_positions = [p for p in exchange.fetch_positions() if float(p.get('contracts', 0)) > 0]

        if balance < BASE_TRADE_SIZE or len(open_positions) >= MAX_OPEN:
            logging.info(f"WAIT | Balance: {balance} | Open: {len(open_positions)}/{MAX_OPEN}")
            time.sleep(40)
            continue

        pick = ask_ai("SCANNER", PROMPTS["SCANNER"].format(symbols=SYMBOLS)).get('pick')
        if not pick or pick in active_trades:
            time.sleep(45)
            continue

        ohlcv = exchange.fetch_ohlcv(pick, '30m', limit=150)
        df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
        chart_path = save_chart(df, pick)

        boss = ask_ai("BOSS", PROMPTS["BOSS"].format(symbol=pick), chart_path)
        hunter = ask_ai("HUNTER", PROMPTS["HUNTER"].format(symbol=pick))
        elder = ask_ai("ELDER", PROMPTS["ELDER"].format(symbol=pick))

        votes = sum(1 for v in [boss.get('vote'), hunter.get('valid'), elder.get('approve')] if v in [True, 'BUY'])
        conf = boss.get('confidence', 0)

        if boss.get('vote') == "BUY" and conf >= MIN_CONFIDENCE and votes >= 2:
            price = df['close'].iloc[-1]
            LEV = get_leverage(pick)
            trade_size = round(min(BASE_TRADE_SIZE * (conf / 100), CAPITAL * 0.20), 2) # ← 20% max ng capital
            amt = round((trade_size * LEV * 0.999) / price, 4)
            amt_half = round(amt / 2, 4)

            exchange.set_margin_mode('isolated', pick)
            exchange.set_leverage(LEV, pick)
            exchange.create_market_buy_order(pick, amt)

            sl = round(price * (1 - SL_PCT), 2)
            tp1 = round(price * (1 + TP1_PCT), 2)
            tp2 = round(price * (1 + TP2_PCT), 2)
            hard_stop = round(price * (1 - HARD_STOP_PCT), 2)

            exchange.create_order(pick, 'STOP_MARKET', 'sell', amt, None, {'stopPrice': sl, 'closeOnTrigger': True, 'reduceOnly': True})
            exchange.create_order(pick, 'TAKE_PROFIT_MARKET', 'sell', amt_half, None, {'stopPrice': tp1, 'closeOnTrigger': True, 'reduceOnly': True})
            exchange.create_order(pick, 'TAKE_PROFIT_MARKET', 'sell', amt_half, None, {'stopPrice': tp2, 'closeOnTrigger': True, 'reduceOnly': True})
            exchange.create_order(pick, 'STOP_MARKET', 'sell', amt, None, {'stopPrice': hard_stop, 'closeOnTrigger': True, 'reduceOnly': True})

            active_trades[pick] = {'entry_price': price}
            msg = f"🚀 LIVE ENTRY → {pick} LONG x{LEV} | BOSS {conf}% | Votes: {votes}/4"
            logging.info(msg)
            tg(msg, chart_path)
        else:
            logging.info(f"NO TRADE | {pick} | Conf: {conf}% | Votes: {votes}/4")

        time.sleep(30)
    except Exception as e:
        logging.error(f"Main error: {e}")
        time.sleep(60)
