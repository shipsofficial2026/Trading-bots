import ccxt, time, requests, json, os, pandas as pd, mplfinance as mpf, logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ====================== V9.9.9 LIVE - BINANCE REAL ======================
IS_LIVE = True

# Load API Keys
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

GROQ_API_KEY_1 = os.getenv('GROQ_API_KEY_1')
GROQ_API_KEY_2 = os.getenv('GROQ_API_KEY_2')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
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

# AI Models Configuration
MODELS = {
    "BOSS":   ["groq", "qwen2.5-72b", GROQ_API_KEY_1],
    "SCANNER":["groq", "llama-3.1-8b-instant", GROQ_API_KEY_2],
    "HUNTER": ["deepseek", "deepseek-chat", DEEPSEEK_API_KEY],
    "ELDER":  ["gemini", "gemini-1.5-flash-latest", GEMINI_API_KEY]
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

# ... (keep the rest of your functions: get_leverage, save_chart, safe_json_parse, ask_ai) ...

# Paste mo na rin yung ibang functions mo (get_leverage, save_chart, safe_json_parse, ask_ai, at yung while loop)

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

        # ... (keep your trading logic) ...

    except Exception as e:
        logging.error(f"Main error: {e}")
        time.sleep(60)
