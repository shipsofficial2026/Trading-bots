cd ~/Trading-bots

rm Bot.py

cat > Bot.py << 'EOF'
import ccxt, time, requests, json, os, pandas as pd, mplfinance as mpf, logging
from datetime import datetime, date
from dotenv import load_dotenv
load_dotenv()
IS_LIVE = False
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
MODELS = {"BOSS":["groq","qwen2.5-72b",GROQ_KEY_1],"SCANNER":["groq","llama-3.1-8b-instant",GROQ_KEY_2],"HUNTER":["deepseek","deepseek-chat",DEEPSEEK_KEY],"ELDER":["gemini","gemini-1.5-flash-latest",GEMINI_KEY]}
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s', handlers=[logging.FileHandler("bot_v9.9.9.log"), logging.StreamHandler()])
exchange = ccxt.binancedm({'apiKey': BINANCE_API,'secret': BINANCE_SECRET,'options': {'defaultType': 'future'},'enableRateLimit': True})
active_trades = {}
def tg(msg: str): 
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg})
    except Exception as e: logging.error(f"TG Error: {e}")
def save_chart(df, symbol): return 'chart.png'
def safe_json_parse(text): 
    text = text.strip().strip('```json').strip('```').strip(); 
    try: return json.loads(text)
    except: return {}
def ask_ai_vision(bot_name, prompt, image_path=None): return {"vote":"BUY","confidence":85} # Simplified muna for test
print(f"🤖 V9.9.9 FINAL | DEMO MODE | Live: {IS_LIVE}")
while True:
    try:
        balance = exchange.fetch_balance()['USDT']['free']
        if balance < BASE_TRADE_SIZE: time.sleep(40); continue
        print(f"DEMO OK | Balance: {balance}")
        time.sleep(30)
    except Exception as e:
        logging.error(f"Main error: {e}")
        time.sleep(60)
EOF
