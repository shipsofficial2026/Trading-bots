import ccxt, time, requests, json, os, pandas as pd, mplfinance as mpf, logging, ta
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ====================== V10.7 - 20X BIG 3, 10X REST ======================
IS_LIVE = True

# API Keys
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
BASE_TRADE_SIZE = 25 # $25 LAHAT
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'TON/USDT', 'ADA/USDT']
MIN_CONFIDENCE = 70
MAX_OPEN = 2
SL_PCT = 0.05 # 5% SL LAHAT
TP1_PCT = 0.10
TP2_PCT = 0.15
TRAIL_ACTIVATE = 0.08
TRAIL_CALLBACK = 0.03
SLEEP_SEC = 300
MAX_DAILY_LOSS_PCT = 0.10
MAX_ATR_PCT = 3.5

# LEVERAGE - 20X BIG 3, 10X IBA
LEVERAGE_MAP = {
    'BTC/USDT': 20, # BIG 3 = 20X
    'ETH/USDT': 20,
    'BNB/USDT': 20,
    'SOL/USDT': 10, # IBA = 10X PARA MAKA-BAWI SA SL
    'XRP/USDT': 10,
    'DOGE/USDT': 10,
    'TON/USDT': 10,
    'ADA/USDT': 10
}
DEFAULT_LEVERAGE = 10

# 4 AI TEAM
MODELS = {
    "BOSS": ["groq", "qwen2.5-72b", GROQ_API_KEY_1],
    "SCANNER": ["deepseek", "deepseek-chat", DEEPSEEK_API_KEY],
    "HUNTER": ["gemini", "gemini-1.5-flash-latest", GEMINI_API_KEY],
    "ELDER": ["openrouter", "meta-llama/llama-3.1-8b-instruct:free", OPENROUTER_API_KEY]
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s',
                    handlers=[logging.FileHandler("bot_v10.7_final.log"), logging.StreamHandler()])

exchange = ccxt.binanceusdm({
    'apiKey': BINANCE_API, 'secret': BINANCE_SECRET,
    'options': {'defaultType': 'future'}, 'enableRateLimit': True
})

STATE_FILE = 'bot_state.json'
active_trades = {}
DAILY_START_BALANCE = 0.0

def save_state():
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({
                'active_trades': active_trades,
                'daily_start_balance': DAILY_START_BALANCE,
                'date': datetime.now(timezone.utc).strftime('%Y-%m-%d')
            }, f)
    except Exception as e: logging.error(f"Save state error: {e}")

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
                DAILY_START_BALANCE = 0.0
    except:
        active_trades = {}
        DAILY_START_BALANCE = 0.0

def tg(msg: str, photo=None):
    try:
        if not TELEGRAM_TOKEN: return
        if photo and os.path.exists(photo):
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                          data={'chat_id': TELEGRAM_CHAT_ID, 'caption': msg, 'parse_mode': 'HTML'},
                          files={'photo': open(photo, 'rb')}, timeout=10)
        else:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'HTML'}, timeout=10)
    except Exception as e: logging.error(f"TG Error: {e}")

def safe_json_parse(text: str) -> dict:
    try:
        start = text.find('{'); end = text.rfind('}') + 1
        return json.loads(text[start:end]) if start!= -1 else {}
    except: return {}

def ask_ai(role, prompt, retries=3):
    name, model, key = MODELS[role]
    if not key: return {}
    url, headers, payload = "", {}, {}
    try:
        if name == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}"}
            payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 200}
        elif name == "deepseek":
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}"}
            payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 200}
        elif name == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
        elif name == "openrouter":
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}"}
            payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 200}

        for attempt in range(retries):
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            if r.status_code == 429:
                wait = 2 ** attempt
                logging.warning(f"{role} rate limited. Wait {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            text = r.json()['candidates'][0]['content']['parts'][0]['text'] if name == "gemini" else r.json()['choices'][0]['message']['content']
            return safe_json_parse(text)
        return {}
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
        mpf.plot(df.tail(100), type='candle', mav=(50,200), style='charles',
                 title=f'{symbol} 30m', savefig=path)
        return path
    except: return None

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
        logging.info(f"Leverage set {symbol}: {lev}x")
        return lev
    except Exception as e:
        logging.error(f"Leverage error {symbol}: {e}")
        return DEFAULT_LEVERAGE

def ensure_sl_tp_exist():
    positions = get_open_positions()
    for pos in positions:
        symbol = pos['symbol']
        contracts = float(pos['contracts'])
        entry = float(pos['entryPrice'])

        if contracts == 0 or symbol not in active_trades: continue

        try:
            orders = exchange.fetch_open_orders(symbol)
            has_sl = any(o['type'] == 'STOP_MARKET' and o['reduceOnly'] for o in orders)

            if not has_sl:
                sl_price = exchange.price_to_precision(symbol, entry * (1 - SL_PCT))
                exchange.create_order(symbol, 'STOP_MARKET', 'sell', contracts, None, {
                    'stopPrice': sl_price, 'reduceOnly': True
                })
                tg(f"⚠️ <b>EMERGENCY SL RECREATED</b>\n{symbol} @ ${sl_price} (5%)")
                logging.error(f"SL missing for {symbol}. Recreated.")
        except Exception as e:
            logging.error(f"SL/TP check error {symbol}: {e}")

def manage_positions():
    positions = get_open_positions()
    for pos in positions:
        symbol = pos['symbol']
        entry = float(pos['entryPrice'])
        current = float(pos['markPrice'])
        contracts = float(pos['contracts'])

        if contracts * current < 5.1: continue

        if symbol not in active_trades:
            active_trades[symbol] = {'entry': entry, 'original_qty': contracts, 'trail_active': False, 'be_moved': False}

        state = active_trades[symbol]
        pnl_pct = (current - entry) / entry

        # 1. Move SL to BE after TP1 hit
        if not state['be_moved'] and contracts < state['original_qty'] * 0.9:
            try:
                orders = exchange.fetch_open_orders(symbol)
                for order in orders:
                    if order['type'] == 'STOP_MARKET' and order['reduceOnly']:
                        new_sl = exchange.price_to_precision(symbol, entry * 1.002)
                        exchange.cancel_order(order['id'], symbol)
                        exchange.create_order(symbol, 'STOP_MARKET', 'sell', contracts, None, {
                            'stopPrice': new_sl, 'reduceOnly': True
                        })
                        state['be_moved'] = True
                        tg(f"🔒 <b>SL MOVED TO BE</b>\n{symbol} @ ${new_sl}\nSecured!")
                        logging.info(f"SL to BE for {symbol}")
                        break
            except Exception as e: logging.error(f"BE move error {symbol}: {e}")

        # 2. Activate trailing stop at +8%
        if not state['trail_active'] and pnl_pct >= TRAIL_ACTIVATE:
            try:
                exchange.cancel_all_orders(symbol)
                exchange.create_order(symbol, 'TRAILING_STOP_MARKET', 'sell', contracts, None, {
                    'callbackRate': TRAIL_CALLBACK * 100, 'reduceOnly': True
                })
                state['trail_active'] = True
                tg(f"📈 <b>TRAILING ACTIVATED</b>\n{symbol} +{pnl_pct*100:.1f}%\nRide it!")
                logging.info(f"Trailing ON {symbol}")
            except Exception as e: logging.error(f"Trail error {symbol}: {e}")

    save_state()

def check_circuit_breaker():
    global DAILY_START_BALANCE
    try:
        total_balance = exchange.fetch_balance()['USDT']['total']
        if DAILY_START_BALANCE == 0.0:
            DAILY_START_BALANCE = total_balance
            save_state()

        daily_pnl = total_balance - DAILY_START_BALANCE
        if daily_pnl < -(CAPITAL * MAX_DAILY_LOSS_PCT):
            tg(f"🛑 <b>CIRCUIT BREAKER</b>\nDaily Loss: ${daily_pnl:.2f}\nTigil muna boss.")
            logging.error(f"MAX DAILY LOSS HIT: ${daily_pnl:.2f}")
            return False
        return True
    except Exception as e:
        logging.error(f"Circuit breaker check error: {e}")
        return True

def execute_trade(pick, last, boss_conf):
    try:
        lev_used = set_leverage(pick)
        trade_size = BASE_TRADE_SIZE # $25 LAHAT
        raw_qty = trade_size / last['close']
        qty = float(exchange.amount_to_precision(pick, raw_qty))
        min_qty = exchange.market(pick)['limits']['amount']['min']

        if qty < min_qty:
            logging.warning(f"QTY {qty} < min {min_qty}. Skip {pick}")
            return False

        order = exchange.create_market_buy_order(pick, qty)
        entry_price = float(order['average']) if order['average'] else last['close']

        sl_price = exchange.price_to_precision(pick, entry_price * (1 - SL_PCT))
        tp1_price = exchange.price_to_precision(pick, entry_price * (1 + TP1_PCT))
        tp2_price = exchange.price_to_precision(pick, entry_price * (1 + TP2_PCT))

        tp1_qty = exchange.amount_to_precision(pick, qty * 0.5)
        tp2_qty = exchange.amount_to_precision(pick, qty * 0.5)

        exchange.create_order(pick, 'STOP_MARKET', 'sell', qty, None, {'stopPrice': sl_price, 'reduceOnly': True})
        exchange.create_order(pick, 'TAKE_PROFIT_MARKET', 'sell', tp1_qty, None, {'stopPrice': tp1_price, 'reduceOnly': True})
        exchange.create_order(pick, 'TAKE_PROFIT_MARKET', 'sell', tp2_qty, None, {'stopPrice': tp2_price, 'reduceOnly': True})

        active_trades = {
            'entry': entry_price,
            'original_qty': qty,
            'trail_active': False,
            'be_moved': False,
            'lev': lev_used,
            'size': trade_size
        }
        save_state()

        risk_amt = trade_size * SL_PCT
        liq_buffer = (1/lev_used - SL_PCT) * 100
        chart_path = save_chart(get_data(pick), pick)
        msg = f"🚀 <b>FINAL BOSS TRADE</b>\n\n" \
              f"<b>Symbol:</b> {pick}\n" \
              f"<b>Entry:</b> ${entry_price:.4f}\n" \
              f"<b>Size:</b> ${trade_size} @ {lev_used}x\n" \
              f"<b>Risk:</b> ${risk_amt:.2f}\n" \
              f"<b>Liq Buffer:</b> {liq_buffer:.1f}%\n" \
              f"<b>Conf:</b> {boss_conf}%\n\n" \
              f"<b>SL:</b> ${sl_price} (5%)\n" \
              f"<b>TP1:</b> ${tp1_price} (+10%)\n" \
              f"<b>TP2:</b> ${tp2_price} (+15%)\n\n" \
              f"<b>LETS GOOO! 🔥</b>"
        tg(msg, chart_path)
        return True
    except Exception as e:
        logging.error(f"Execute error {pick}: {e}")
        tg(f"⚠️ <b>EXECUTE FAILED</b>\n{pick}\n{str(e)[:100]}")
        return False

# ====================== MAIN LOOP ======================
load_state()
logging.info(f"🤖 V10.7 FINAL | 20x BIG 3 | 10x REST | $25 ALL | 5% SL")
tg(f"🤖 <b>V10.7 FINAL BOSS</b>\n\n<b>20x:</b> BTC/ETH/BNB\n<b>10x:</b> SOL/XRP/DOGE/ADA/TON\n<b>Size:</b> $25 ALL\n<b>SL:</b> 5% ALL\n<b>Risk:</b> $1.25/trade\n\n<b>WALANG TAKOT TAKOT\nTIBA-TIBA TAYO! 🔥🔥🔥</b>")

while True:
    try:
        start_time = time.time()

        if not check_circuit_breaker(): break

        ensure_sl_tp_exist()
        manage_positions()

        balance = exchange.fetch_balance()['USDT']['free']
        open_positions = get_open_positions()

        if balance < BASE_TRADE_SIZE or len(open_positions) >= MAX_OPEN:
            logging.info(f"WAIT | Balance: ${balance:.2f} | Open: {len(open_positions)}/{MAX_OPEN}")
            time.sleep(SLEEP_SEC)
            continue

        # 1. SCANNER
        prompt = f"Pick 1 coin with strongest 30m uptrend from: {SYMBOLS}. Avoid: {[p['symbol'] for p in open_positions]}. Prefer 20x coins BTC/ETH/BNB and 10x meme DOGE for fast gains. Return ONLY JSON: {{\"pick\":\"BTC/USDT\",\"reason\":\"strong trend\"}}"
        scan = ask_ai("SCANNER", prompt)
        pick = scan.get('pick')
        if not pick or pick in [p['symbol'] for p in open_positions]:
            time.sleep(SLEEP_SEC)
            continue

        df = get_data(pick)
        last = df.iloc[-1]
        if pd.isna(last['ema50']) or pd.isna(last['ema200']) or pd.isna(last['atr']):
            time.sleep(SLEEP_SEC)
            continue

        atr_pct = (last['atr'] / last['close']) * 100
        if atr_pct > MAX_ATR_PCT:
            logging.info(f"SKIP {pick} - ATR {atr_pct:.1f}% > {MAX_ATR_PCT}%")
            time.sleep(SLEEP_SEC)
            continue

        # 2. BOSS - TREND CHECK
        trend_ok = last['close'] > last['ema200'] and last['ema50'] > last['ema200']
        lev = LEVERAGE_MAP.get(pick, DEFAULT_LEVERAGE)
        prompt = f"Analyze {pick} 30m. Price:{last['close']:.4f}, EMA50:{last['ema50']:.4f}, EMA200:{last['ema200']:.4f}, RSI:{last['rsi']:.1f}, ATR:{atr_pct:.1f}%, Lev:{lev}x. Trend OK:{trend_ok}. USER SAID WALANG TAKOT. Return ONLY JSON: {{\"vote\":\"BUY\",\"confidence\":85,\"reason\":\"trend up\"}}"
        boss = ask_ai("BOSS", prompt)
        if boss.get('vote')!= 'BUY' or boss.get('confidence', 0) < MIN_CONFIDENCE:
            logging.info(f"BOSS REJECT {pick} | Conf: {boss.get('confidence')}")
            time.sleep(SLEEP_SEC)
            continue

        # 3. HUNTER - ENTRY
        prompt = f"Good entry for LONG {pick} now? RSI:{last['rsi']:.1f}, ATR:{atr_pct:.1f}%, Lev:{lev}x. Need aggressive entries. Return ONLY JSON: {{\"valid\":true}}"
        hunter = ask_ai("HUNTER", prompt)
        if not hunter.get('valid'):
            logging.info(f"HUNTER REJECT {pick}")
            time.sleep(SLEEP_SEC)
            continue

        # 4. ELDER - RISK
        prompt = f"Safe to risk $25 on {pick} with ${balance:.2f} balance? Max {MAX_OPEN} trades, {lev}x lev, 5% SL. User accepts risk for big gains. Return ONLY JSON: {{\"approve\":true}}"
        elder = ask_ai("ELDER", prompt)
        if not elder.get('approve'):
            logging.info(f"ELDER REJECT {pick}")
            time.sleep(SLEEP_SEC)
            continue

        # 5. EXECUTE - 4/4 APPROVED
        logging.info(f"✅ 4 AI APPROVED! {pick} | {lev}x $25 | ATR:{atr_pct:.1f}% | Conf:{boss.get('confidence')}% | LETS GO!")
        execute_trade(pick, last, boss.get('confidence'))

        elapsed = time.time() - start_time
        time.sleep(max(0, SLEEP_SEC - elapsed))

    except KeyboardInterrupt:
        tg("🛑 <b>BOT STOPPED MANUALLY</b>")
        break
    except Exception as e:
        logging.error(f"Main loop error: {e}")
        tg(f"⚠️ <b>BOT ERROR</b>\n{str(e)[:200]}")
        time.sleep(120)

logging.info("Bot shutdown.")
