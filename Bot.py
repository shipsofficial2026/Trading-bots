import ccxt, time, requests, json, os, pandas as pd, mplfinance as mpf, logging
from datetime import date
from dotenv import load_dotenv
load_dotenv()

# ====================== V10.0.3 FINAL - BINANCE DEMO TRADING ======================
IS_LIVE = False # FALSE = DEMO. TRUE = REAL MONEY. DANGER!

# ====================== KEYS ======================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GROQ_KEY_1 = os.getenv('GROQ_KEY_1')
GROQ_KEY_2 = os.getenv('GROQ_KEY_2')
DEEPSEEK_KEY = os.getenv('DEEPSEEK_KEY')
GEMINI_KEY = os.getenv('GEMINI_KEY')
BINANCE_API = os.getenv('BINANCE_API') # Gamitin mo DEMO API KEY dito boss
BINANCE_SECRET = os.getenv('BINANCE_SECRET') # Galing sa demo.binance.com

CAPITAL = 1000.0
BASE_TRADE_SIZE = 200
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT']
MIN_CONFIDENCE = 78

MODELS = {
    "BOSS": ["groq", "qwen2.5-72b", GROQ_KEY_1],
    "SCANNER":["groq", "llama-3.1-8b-instant", GROQ_KEY_2],
    "HUNTER": ["deepseek", "deepseek-chat", DEEPSEEK_KEY],
    "ELDER": ["gemini", "gemini-1.5-flash-latest", GEMINI_KEY]
}

PROMPTS = {
    "BOSS": """You are an elite 24/7 crypto trader. Analyze {symbol} 30m chart.
    Price > EMA200 and EMA50 > EMA200 = BUY. Return ONLY JSON: {{"vote":"BUY","confidence":85}}""",
    "SCANNER": "Pick 1 best long: {symbols}. Return ONLY: {{\"pick\":\"BTC/USDT\"}}",
    "HUNTER": "Valid long on {symbol}? Return ONLY: {{\"valid\":true}}",
    "ELDER": "Safe to LONG {symbol}? Return ONLY: {{\"approve\":true}}"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', handlers=[logging.StreamHandler()])

# ========= ITO NA YUNG BAGO BOSS =========
# ccxt v4.5.6+ = enable_demo_trading(True)【7745167443875226477†L96-L98】
exchange = ccxt.binanceusdm({
    'apiKey': BINANCE_API,
    'secret': BINANCE_SECRET,
    'options': {'defaultType': 'future'},
    'enableRateLimit': True
})
exchange.enable_demo_trading(True) # <--- BINANCE DEMO MODE. FAKE MONEY LANG

def save_chart(df, symbol):
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[['open','high','low','close','volume']]
    df.columns = ['Open','High','Low','Close','Volume']
    apds = [mpf.make_addplot(df['Close'].ewm(span=50).mean(), color='blue'),
            mpf.make_addplot(df['Close'].ewm(span=200).mean(), color='orange')]
    mpf.plot(df[-100:], type='candle', style='yahoo', addplot=apds, title=f'{symbol} 30m', savefig='chart.png', volume=True)
    return 'chart.png'

def safe_json_parse(text):
    text = text.strip().strip('```json').strip('```').strip()
    try: return json.loads(text)
    except: return {}

def ask_ai(bot_name, prompt, image_path=None):
    provider, model, key = MODELS[bot_name]
    if not key: return {}
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

logging.info(f"🤖 V10.0.3 FINAL | AI BOSS TEAM | DEMO TRADING MODE | Live: {IS_LIVE}")

while True:
    try:
        balance = exchange.fetch_balance()['USDT']['free']
        if balance < BASE_TRADE_SIZE:
            time.sleep(40)
            continue

        pick = ask_ai("SCANNER", PROMPTS["SCANNER"].format(symbols=SYMBOLS)).get('pick')
        if not pick:
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
            logging.info(f"🚀 DEMO SIGNAL → {pick} LONG | BOSS {conf}% | Votes: {votes}/4")
        else:
            logging.info(f"NO TRADE | {pick} | Conf: {conf}% | Votes: {votes}/4")

        time.sleep(30)
    except Exception as e:
        logging.error(f"Main error: {e}")
        time.sleep(60)
