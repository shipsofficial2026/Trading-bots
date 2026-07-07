import ccxt, time, requests, json, os, pandas as pd, mplfinance as mpf, logging, ta
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ====================== V10.9 - FULL UPDATE ======================
IS_LIVE = True

# ====================== CONFIG ======================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GROQ_API_KEY_1 = os.getenv('GROQ_API_KEY_1')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
BINANCE_API = os.getenv('BINANCE_API')
BINANCE_SECRET = os.getenv('BINANCE_SECRET')

# Trading Parameters
CAPITAL = 60.0
BASE_TRADE_SIZE = 25.0
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'TON/USDT', 'ADA/USDT']
MIN_CONFIDENCE = 70
MAX_OPEN = 2
SL_PCT = 0.05
TP1_PCT = 0.10
TP2_PCT = 0.15
TRAIL_ACTIVATE = 0.08
TRAIL_CALLBACK = 0.03
SLEEP_SEC = 180
MAX_DAILY_LOSS_PCT = 0.10
MAX_ATR_PCT = 3.5

LEVERAGE_MAP = {
    'BTC/USDT': 20, 'ETH/USDT': 20, 'BNB/USDT': 20,
    'SOL/USDT': 10, 'XRP/USDT': 10, 'DOGE/USDT': 10,
    'TON/USDT': 10, 'ADA/USDT': 10
}
DEFAULT_LEVERAGE = 10

MODELS = {
    "BOSS": ["groq", "qwen2.5-72b", GROQ_API_KEY_1],
    "SCANNER": ["deepseek", "deepseek-chat", DEEPSEEK_API_KEY],
    "HUNTER": ["gemini", "gemini-1.5-flash-latest", GEMINI_API_KEY],
    "ELDER": ["openrouter", "meta-llama/llama-3.1-8b-instruct:free", OPENROUTER_API_KEY]
}

# ====================== SETUP ======================
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s | %(levelname)s | %(message)s',
                    handlers=[logging.FileHandler("bot_v10.9.log"), logging.StreamHandler()])

exchange = ccxt.binanceusdm({
    'apiKey': BINANCE_API,
    'secret': BINANCE_SECRET,
    'options': {'defaultType': 'future'},
    'enableRateLimit': True
})

exchange.load_markets()

STATE_FILE = 'bot_state.json'
active_trades = {}
DAILY_START_BALANCE = 0.0

# ====================== HELPER FUNCTIONS ======================
def save_state():
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({
                'active_trades': active_trades,
                'daily_start_balance': DAILY_START_BALANCE,
                'date': datetime.now(timezone.utc).strftime('%Y-%m-%d')
            }, f, indent=2)
    except Exception as e:
        logging.error(f"Save state error: {e}")

def load_state():
    global active_trades, DAILY_START_BALANCE
    try:
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
            today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            if data.get('date') == today:
                active_trades = data.get('active_trades', {})
                DAILY_START_BALANCE = data.get('daily_start_balance', 0.0)
            else:
                active_trades = {}
                DAILY_START_BALANCE = 0.0
    except:
        active_trades = {}
        DAILY_START_BALANCE = 0.0

def tg(msg: str, photo=None):
    try:
        if not TELEGRAM_TOKEN:
            return
        if photo and os.path.exists(photo):
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                          data={'chat_id': TELEGRAM_CHAT_ID, 'caption': msg, 'parse_mode': 'HTML'},
                          files={'photo': open(photo, 'rb')}, timeout=15)
        else:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'HTML'}, timeout=10)
    except Exception as e:
        logging.error(f"TG Error: {e}")

def safe_json_parse(text: str):
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
        return {}
    except:
        return {}

def ask_ai(role, prompt):
    name, model, key = MODELS[role]
    if not key:
        return {}
    try:
        if name == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, json=payload, timeout=30)
        else:
            url_dict = {
                "groq": "https://api.groq.com/openai/v1/chat/completions",
                "deepseek": "https://api.deepseek.com/v1/chat/completions",
                "openrouter": "https://openrouter.ai/api/v1/chat/completions"
            }
            url = url_dict[name]
            headers = {"Authorization": f"Bearer {key}"}
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 250
            }
            r = requests.post(url, headers=headers, json=payload, timeout=30)

        r.raise_for_status()
        data = r.json()
        
        if name == "gemini":
            text = data['candidates'][0]['content']['parts'][0]['text']
        else:
            text = data['choices'][0]['message']['content']
        
        return safe_json_parse(text)
    except Exception as e:
        logging.error(f"{role} AI Error: {e}")
        return {}

def get_data(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, '30m', limit=200)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['ema50'] = ta.trend.ema_indicator(df['close'], 50)
    df['ema200'] = ta.trend.ema_indicator(df['close'], 200)
    df['rsi'] = ta.momentum.rsi(df['close'], 14)
    df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], 14)
    return df

def save_chart(df, symbol):
    try:
        path = f'chart_{symbol.replace("/","")}.png'
        mpf.plot(df.tail(100), type='candle', mav=(50, 200), style='charles',
                 title=f'{symbol} 30m', savefig=path, figsize=(12, 8))
        return path
    except:
        return None

def get_open_positions():
    try:
        positions = exchange.fetch_positions()
        return [p for p in positions if float(p.get('contracts', 0)) > 0 and p['symbol'] in SYMBOLS]
    except Exception as e:
        logging.error(f"Fetch positions error: {e}")
        return []

def set_leverage(symbol):
    try:
        lev = LEVERAGE_MAP.get(symbol, DEFAULT_LEVERAGE)
        exchange.set_leverage(lev, symbol)
        return lev
    except:
        return DEFAULT_LEVERAGE

# ====================== CORE FUNCTIONS ======================
def ensure_sl_tp_exist():
    positions = get_open_positions()
    for pos in positions:
        symbol = pos['symbol']
        if symbol not in active_trades: continue
        try:
            orders = exchange.fetch_open_orders(symbol)
            has_sl = any(o['type'] == 'STOP_MARKET' and o.get('reduceOnly') for o in orders)
            if not has_sl:
                entry = float(pos['entryPrice'])
                contracts = float(pos['contracts'])
                sl_price = exchange.price_to_precision(symbol, entry * (1 - SL_PCT))
                exchange.create_order(symbol, 'STOP_MARKET', 'sell', contracts, None,
                                    {'stopPrice': sl_price, 'reduceOnly': True})
                tg(f"⚠️ <b>EMERGENCY SL RECREATED</b>\n{symbol}")
        except Exception as e:
            logging.error(f"SL Check Error {symbol}: {e}")

def manage_positions():
    positions = get_open_positions()
    for pos in positions:
        symbol = pos['symbol']
        if symbol not in active_trades: continue
            
        state = active_trades[symbol]
        entry = float(pos['entryPrice'])
        current = float(pos['markPrice'])
        contracts = float(pos['contracts'])
        pnl_pct = (current - entry) / entry

        if not state.get('be_moved') and contracts < state['original_qty'] * 0.9:
            try:
                orders = exchange.fetch_open_orders(symbol)
                for o in orders:
                    if o['type'] == 'STOP_MARKET' and o.get('reduceOnly'):
                        new_sl = exchange.price_to_precision(symbol, entry * 1.002)
                        exchange.cancel_order(o['id'], symbol)
                        exchange.create_order(symbol, 'STOP_MARKET', 'sell', contracts, None,
                                            {'stopPrice': new_sl, 'reduceOnly': True})
                        state['be_moved'] = True
                        tg(f"🔒 <b>SL MOVED TO BE</b>\n{symbol}")
                        break
            except Exception as e:
                logging.error(f"BE move error: {e}")

        if not state.get('trail_active') and pnl_pct >= TRAIL_ACTIVATE:
            try:
                exchange.cancel_all_orders(symbol)
                exchange.create_order(symbol, 'TRAILING_STOP_MARKET', 'sell', contracts, None,
                                    {'callbackRate': TRAIL_CALLBACK * 100, 'reduceOnly': True})
                state['trail_active'] = True
                tg(f"📈 <b>TRAILING ACTIVATED</b>\n{symbol} +{pnl_pct*100:.1f}%")
            except Exception as e:
                logging.error(f"Trailing error: {e}")

    save_state()

def check_circuit_breaker():
    global DAILY_START_BALANCE
    try:
        total = exchange.fetch_balance()['USDT']['total']
        if DAILY_START_BALANCE == 0.0:
            DAILY_START_BALANCE = total
            save_state()

        daily_pnl = total - DAILY_START_BALANCE
        if daily_pnl < -(CAPITAL * MAX_DAILY_LOSS_PCT):
            tg(f"🛑 <b>CIRCUIT BREAKER ACTIVATED</b>\nDaily Loss: ${daily_pnl:.2f}")
            return False
        return True
    except:
        return True

def execute_trade(pick, last, boss_conf):
    try:
        lev_used = set_leverage(pick)
        raw_qty = BASE_TRADE_SIZE / last['close']
        qty = float(exchange.amount_to_precision(pick, raw_qty))

        if qty < exchange.market(pick)['limits']['amount']['min']:
            return False

        order = exchange.create_market_buy_order(pick, qty)
        entry_price = float(order.get('average') or last['close'])

        sl_price = exchange.price_to_precision(pick, entry_price * (1 - SL_PCT))
        tp1_price = exchange.price_to_precision(pick, entry_price * (1 + TP1_PCT))
        tp2_price = exchange.price_to_precision(pick, entry_price * (1 + TP2_PCT))

        tp1_qty = exchange.amount_to_precision(pick, qty * 0.5)
        tp2_qty = exchange.amount_to_precision(pick, qty * 0.5)

        exchange.create_order(pick, 'STOP_MARKET', 'sell', qty, None, {'stopPrice': sl_price, 'reduceOnly': True})
        exchange.create_order(pick, 'TAKE_PROFIT_MARKET', 'sell', tp1_qty, None, {'stopPrice': tp1_price, 'reduceOnly': True})
        exchange.create_order(pick, 'TAKE_PROFIT_MARKET', 'sell', tp2_qty, None, {'stopPrice': tp2_price, 'reduceOnly': True})

        active_trades[pick] = {
            'entry': entry_price,
            'original_qty': qty,
            'trail_active': False,
            'be_moved': False,
            'lev': lev_used,
            'size': BASE_TRADE_SIZE
        }
        save_state()

        chart_path = save_chart(get_data(pick), pick)
        msg = f"🚀 <b>FINAL BOSS TRADE EXECUTED</b>\n\n" \
              f"<b>Symbol:</b> {pick}\n" \
              f"<b>Entry:</b> ${entry_price:.4f}\n" \
              f"<b>Size:</b> ${BASE_TRADE_SIZE} @ {lev_used}x\n" \
              f"<b>Risk:</b> ${BASE_TRADE_SIZE * SL_PCT:.2f}\n" \
              f"<b>Confidence:</b> {boss_conf}%\n\n" \
              f"SL: ${sl_price} (5%)\n" \
              f"TP1: ${tp1_price} (+10%)\n" \
              f"TP2: ${tp2_price} (+15%)\n\n" \
              f"<b>LETS GOOO! 🔥</b>"

        tg(msg, chart_path)
        return True

    except Exception as e:
        logging.error(f"Execute error {pick}: {e}")
        tg(f"⚠️ EXECUTE FAILED\n{pick}\n{str(e)[:100]}")
        return False

# ====================== START BOT ======================
load_state()
logging.info("🤖 V10.9 FINAL BOSS BOT STARTED")
tg("🤖 <b>V10.9 FULL UPDATE</b>\n20x BIG 3 | 10x REST | $25 ALL | 5% SL\n<b>WALANG TAKOT! 🔥</b>")

while True:
    try:
        start_time = time.time()

        if not check_circuit_breaker():
            break

        ensure_sl_tp_exist()
        manage_positions()

        balance = exchange.fetch_balance()['USDT']['free']
        open_positions = get_open_positions()

        # Sync active_trades with real positions
        current_symbols = {p['symbol'] for p in open_positions}
        for sym in list(active_trades.keys()):
            if sym not in current_symbols:
                del active_trades[sym]
        save_state()

        if balance < BASE_TRADE_SIZE or len(open_positions) >= MAX_OPEN:
            logging.info(f"Waiting | Balance: ${balance:.2f} | Open: {len(open_positions)}/{MAX_OPEN}")
            time.sleep(SLEEP_SEC)
            continue

        # 1. SCANNER
        prompt = f"Pick 1 strongest 30m uptrend coin from: {SYMBOLS}. Avoid open positions. Prefer BTC/ETH/BNB. Return ONLY JSON: {{\"pick\":\"BTC/USDT\",\"reason\":\"strong trend\"}}"
        scan = ask_ai("SCANNER", prompt)
        pick = scan.get('pick')
        if not pick or pick in [p['symbol'] for p in open_positions]:
            time.sleep(SLEEP_SEC)
            continue

        df = get_data(pick)
        last = df.iloc[-1]

        # NaN Check
        if pd.isna(last['ema50']) or pd.isna(last['ema200']) or pd.isna(last['rsi']) or pd.isna(last['atr']):
            logging.info(f"Insufficient data for {pick}")
            time.sleep(SLEEP_SEC)
            continue

        atr_pct = (last['atr'] / last['close']) * 100
        if atr_pct > MAX_ATR_PCT:
            logging.info(f"High ATR skip {pick} {atr_pct:.1f}%")
            time.sleep(SLEEP_SEC)
            continue

        # 2. BOSS
        trend_ok = last['close'] > last['ema200'] and last['ema50'] > last['ema200']
        lev = LEVERAGE_MAP.get(pick, DEFAULT_LEVERAGE)
        prompt = f"Analyze {pick} 30m. Price:{last['close']:.4f}, EMA50:{last['ema50']:.4f}, EMA200:{last['ema200']:.4f}, RSI:{last['rsi']:.1f}, ATR:{atr_pct:.1f}%. Trend OK: {trend_ok}. Return ONLY JSON: {{\"vote\":\"BUY\",\"confidence\":85,\"reason\":\"...\"}}"
        boss = ask_ai("BOSS", prompt)
        if boss.get('vote') != 'BUY' or boss.get('confidence', 0) < MIN_CONFIDENCE:
            time.sleep(SLEEP_SEC)
            continue

        # 3. HUNTER + 4. ELDER
        hunter = ask_ai("HUNTER", f"Is now a good aggressive LONG entry for {pick}? Price near EMA50, RSI:{last['rsi']:.1f}, ATR:{atr_pct:.1f}%. Return ONLY JSON: {{\"valid\":true}}")
        elder = ask_ai("ELDER", f"Safe to risk ${BASE_TRADE_SIZE} on {pick} with ${balance:.2f} balance?")

        if not hunter.get('valid', True) or not elder.get('approve', True):
            time.sleep(SLEEP_SEC)
            continue

        # EXECUTE
        logging.info(f"✅ 4/4 APPROVED → {pick} | {lev}x | Conf:{boss.get('confidence')}%")
        execute_trade(pick, last, boss.get('confidence', 75))

        time.sleep(max(0, SLEEP_SEC - (time.time() - start_time)))

    except KeyboardInterrupt:
        tg("🛑 Bot stopped manually")
        break
    except Exception as e:
        logging.error(f"Main loop error: {e}")
        tg(f"⚠️ BOT ERROR\n{str(e)[:150]}")
        time.sleep(60)

logging.info("Bot shutdown.")
