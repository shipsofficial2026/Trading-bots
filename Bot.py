import ccxt, time, requests, json, os, pandas as pd, mplfinance as mpf, logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ====================== V9.9.12 OPENROUTER EDITION ======================
IS_LIVE = True

# Load API Keys - 1 GROQ LANG + DAGDAG OPENROUTER
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

GROQ_API_KEY_1 = os.getenv('GROQ_API_KEY_1') # Si BOSS lang gagamit nito
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY') # <-- Bagong AI to
BINANCE_API = os.getenv('BINANCE_API')
BINANCE_SECRET = os.getenv('BINANCE_SECRET')

# Trading Parameters
CAPITAL = 60.0
BASE_TRADE_SIZE = 25
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'TON/USDT', 'ADA/USDT']
MIN_CONFIDENCE = 78
MAX_OPEN = 2
SL_PCT = 0.05
TP1_PCT = 0.10
TP2_PCT = 0.15
HARD_STOP_PCT = 0.07
SLEEP_SEC = 75 # Pina-safe: 75s para di magban kay Groq

# AI Models Configuration - 4 AI TEAM, 1 GROQ LANG
MODELS = {
    "BOSS": ["groq", "qwen2.5-72b", GROQ_API_KEY_1], # Pinaka-matalino
    "SCANNER": ["deepseek", "deepseek-chat", DEEPSEEK_API_KEY], # Bilis mag-scan
    "HUNTER": ["gemini", "gemini-1.5-flash-latest", GEMINI_API_KEY], # Stable
    "ELDER": ["openrouter", "meta-llama/llama-3.1-8b-instruct:free", OPENROUTER_API_KEY] # Libre backup
}

PROMPTS = {
    "BOSS": """You are an elite 24/7 crypto trader. Analyze this 30m chart of {symbol}.
Rules: Price > EMA200, EMA50 > EMA200. Return ONLY JSON: {{"vote":"BUY","confidence":85,"reason":"short"}}""",
    "SCANNER": "Pick the SINGLE strongest long: {symbols}. Return ONLY: {{\"pick\":\"BTC/USDT\"}}",
    "HUNTER": "Valid long on {symbol} 30m? Return ONLY: {{\"valid\":true}}",
    "ELDER": "Safe to LONG {symbol}? Return ONLY: {{\"approve\":true}}"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s',
                    handlers=[logging.FileHandler("bot_v9.9.12_live.log"), logging.StreamHandler()])

# Binance Futures Setup
exchange = ccxt.binanceusdm({
    'apiKey': BINANCE_API,
    'secret': BINANCE_SECRET,
    'options': {'defaultType': 'future'},
    'enableRateLimit': True
})
exchange.enable_demo_trading(False)

active_trades = {}

def tg(msg: str, photo=None):
    try:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            return
        if photo and os.path.exists(photo):
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                          data={'chat_id': TELEGRAM_CHAT_ID, 'caption': msg},
                          files={'photo': open(photo, 'rb')}, timeout=10)
        else:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg}, timeout=10)
    except Exception as e:
        logging.error(f"TG Error: {e}")

def safe_json_parse(text: str) -> dict:
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        return json.loads(text[start:end]) if start!= -1 else {}
    except:
        return {}

def ask_ai(role, prompt):
    name, model, key = MODELS[role]
    url, headers, payload = "", {}, {}
    if name == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 150}
    elif name == "deepseek":
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 150}
    elif name == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
    elif name == "openrouter": # <-- Bagong block to
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "HTTP-Referer": "CryptoBot", "X-Title": "AI Trading Bot"}
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 150}

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=25)
        if r.status_code == 429:
            logging.warning(f"{role} | Rate limited. Sleep 90s")
            time.sleep(90)
            return {}
        r.raise_for_status()
        if name == "gemini":
            text = r.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            text = r.json()['choices'][0]['message']['content']
        return safe_json_parse(text)
    except Exception as e:
        logging.error(f"{role} AI Error: {e}")
        return {}

logging.info(f"🤖 V9.9.12 | GROQ + DEEPSEEK + GEMINI + OPENROUTER | SLEEP {SLEEP_SEC}s | LIVE: {IS_LIVE}")

while True:
    try:
        balance = exchange.fetch_balance()['USDT']['free']
        open_positions = [p for p in exchange.fetch_positions() if float(p.get('contracts', 0)) > 0]

        if balance < BASE_TRADE_SIZE or len(open_positions) >= MAX_OPEN:
            logging.info(f"WAIT | Balance: {balance} | Open: {len(open_positions)}/{MAX_OPEN}")
            time.sleep(SLEEP_SEC)
            continue

        pick = ask_ai("SCANNER", PROMPTS["SCANNER"].format(symbols=SYMBOLS)).get('pick')
        if not pick or pick in active_trades:
            time.sleep(SLEEP_SEC)
            continue

        logging.info(f"SCAN PICK: {pick}")
        #... dito mo na ilagay yung BOSS, HUNTER, ELDER logic mo...
        time.sleep(SLEEP_SEC)

    except Exception as e:
        logging.error(f"Main error: {e}")
        time.sleep(120)
