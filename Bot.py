import ccxt
import time
import requests
import json
import os
import pandas as pd
import mplfinance as mpf
import logging
import ta
import re
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ====================== V11.2-FREE - GROQ RESTORED ======================
IS_LIVE = True  # TRUE = LIVE, FALSE = PAPER

# ====================== CONFIG ======================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')           # Clean Groq
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
BINANCE_API = os.getenv('BINANCE_API')
BINANCE_SECRET = os.getenv('BINANCE_SECRET')

# Trading Parameters
CAPITAL = 150.0
BASE_TRADE_SIZE = 50.0
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'TON/USDT', 'ADA/USDT']
MIN_CONFIDENCE = 70
MAX_OPEN = 3

SL_PCT = 0.04
TP1_PCT = 0.09
TP2_PCT = 0.15
TP3_PCT = 0.22
TRAIL_ACTIVATE = 0.10
TRAIL_CALLBACK = 0.04

SLEEP_SEC = 180
MAX_DAILY_LOSS_PCT = 0.10
MAX_ATR_PCT = 3.5

LEVERAGE_MAP = {
    'BTC/USDT': 20, 'ETH/USDT': 20, 'BNB/USDT': 20,
    'SOL/USDT': 10, 'XRP/USDT': 10, 'DOGE/USDT': 10,
    'TON/USDT': 10, 'ADA/USDT': 10
}
DEFAULT_LEVERAGE = 10

# AI Models
MODELS = {
    "BOSS": ["groq", "llama-3.1-70b-versatile", GROQ_API_KEY],
    "HUNTER": ["gemini", "gemini-1.5-flash-latest", GEMINI_API_KEY],
    "ELDER": ["openrouter", "meta-llama/llama-3.1-8b-instruct:free", OPENROUTER_API_KEY]
}

# ====================== SETUP ======================
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s | %(levelname)s | %(message)s',
                    handlers=[logging.FileHandler("bot_v11.2-free.log"), logging.StreamHandler()])

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
        if not TELEGRAM_TOKEN: return
        if photo and os.path.exists(photo):
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                          data={'chat_id': TELEGRAM_CHAT_ID, 'caption': msg, 'parse_mode': 'HTML'},
                          files={'photo': open(photo, 'rb')}, timeout=15)
            os.remove(photo)
        else:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'HTML'}, timeout=10)
    except Exception as e:
        logging.error(f"TG Error: {e}")

def safe_json_parse(text: str):
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        return json.loads(match.group(0)) if match else {}
    except:
        return {}

def ask_ai(role, prompt):
    name, model, key = MODELS[role]
    if not key:
        logging.warning(f"No API key for {role}")
        return {}
    try:
        if name == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, json=payload, timeout=30)
            text = r.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            url = "https://api.groq.com/openai/v1/chat/completions" if name == "groq" else "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}"}
            payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 300}
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            text = r.json()['choices'][0]['message']['content']
        return safe_json_parse(text)
    except Exception as e:
        logging.error(f"{role} AI Error: {e}")
        return {}

def get_data(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, '30m', limit=200)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df['ema50'] = ta.trend.ema_indicator(df['close'], 50)
    df['ema200'] = ta.trend.ema_indicator(df['close'], 200)
    df['rsi'] = ta.momentum.rsi(df['close'], 14)
    df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], 14)
    return df

def save_chart(df, symbol):
    try:
        path = f'chart_{symbol.replace("/","")}.png'
        mpf.plot(df.tail(100), type='candle', mav=(50, 200), style='charles',
                 title=f'{symbol} 30m | V11.2-FREE', savefig=path, figsize=(12, 8))
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
        exchange.set_margin_mode('ISOLATED', symbol)
        exchange.set_position_mode(False)
        logging.info(f"Leverage set {symbol}: {lev}x ISOLATED")
        return lev
    except Exception as e:
        logging.error(f"Leverage error {symbol}: {e}")
        return DEFAULT_LEVERAGE

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
                sl_order = exchange.create_order(symbol, 'STOP_MARKET', 'sell', contracts, None, {'stopPrice': sl_price, 'reduceOnly': True})
                active_trades[symbol]['sl_order_id'] = sl_order['id']
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

        if not state.get('be_moved') and pnl_pct >= 0.035:
            try:
                orders = exchange.fetch_open_orders(symbol)
                for o in orders:
                    if o['type'] == 'STOP_MARKET' and o.get('reduceOnly') and o['id'] == state.get('sl_order_id'):
                        new_sl = exchange.price_to_precision(symbol, entry * 1.002)
                        exchange.cancel_order(o['id'], symbol)
                        new_sl_order = exchange.create_order(symbol, 'STOP_MARKET', 'sell', contracts, None, {'stopPrice': new_sl, 'reduceOnly': True})
                        state['be_moved'] = True
                        state['sl_order_id'] = new_sl_order['id']
                        tg(f"🔒 <b>SL MOVED TO BE+0.2%</b>\n{symbol} +{pnl_pct*100:.1f}%")
                        break
            except Exception as e:
                logging.error(f"BE move error: {e}")

        if not state.get('trail_active') and pnl_pct >= TRAIL_ACTIVATE:
            try:
                orders = exchange.fetch_open_orders(symbol)
                for o in orders:
                    if o['type'] == 'STOP_MARKET' and o.get('reduceOnly') and o['id'] == state.get('sl_order_id'):
                        exchange.cancel_order(o['id'], symbol)
                        break

                activation_price = exchange.price_to_precision(symbol, entry * (1 + TRAIL_ACTIVATE))
                exchange.create_order(symbol, 'TRAILING_STOP_MARKET', 'sell', contracts, None, {
                    'callbackRate': TRAIL_CALLBACK * 100,
                    'reduceOnly': True,
                    'activationPrice': activation_price
                })
                state['trail_active'] = True
                tg(f"📈 <b>TRAILING ACTIVATED</b>\n{symbol} +{pnl_pct*100:.1f}%\nTrail: {TRAIL_CALLBACK*100:.1f}%")
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
            tg(f"🛑 <b>CIRCUIT BREAKER ACTIVATED</b>\nDaily Loss: ${daily_pnl:.2f}\nBot stopped for 1 hour.")
            return False
        return True
    except:
        return True

def execute_trade(pick, last, boss_conf):
    if not IS_LIVE:
        logging.info(f"📝 PAPER TRADE: {pick} ${BASE_TRADE_SIZE} @ {LEVERAGE_MAP.get(pick, DEFAULT_LEVERAGE)}x")
        tg(f"📝 <b>PAPER TRADE</b>\n{pick}\nEntry: ${last['close']:.4f}\nConf: {boss_conf}%")
        return True

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
        tp3_price = exchange.price_to_precision(pick, entry_price * (1 + TP3_PCT))

        tp1_qty = exchange.amount_to_precision(pick, qty * 0.50)
        tp2_qty = exchange.amount_to_precision(pick, qty * 0.30)
        tp3_qty = exchange.amount_to_precision(pick, qty * 0.15)

        sl_order = exchange.create_order(pick, 'STOP_MARKET', 'sell', qty, None, {'stopPrice': sl_price, 'reduceOnly': True})
        tp1_order = exchange.create_order(pick, 'TAKE_PROFIT_MARKET', 'sell', tp1_qty, None, {'stopPrice': tp1_price, 'reduceOnly': True})
        tp2_order = exchange.create_order(pick, 'TAKE_PROFIT_MARKET', 'sell', tp2_qty, None, {'stopPrice': tp2_price, 'reduceOnly': True})
        tp3_order = exchange.create_order(pick, 'TAKE_PROFIT_MARKET', 'sell', tp3_qty, None, {'stopPrice': tp3_price, 'reduceOnly': True})

        active_trades[pick] = {
            'entry': entry_price,
            'original_qty': qty,
            'trail_active': False,
            'be_moved': False,
            'lev': lev_used,
            'size': BASE_TRADE_SIZE,
            'sl_order_id': sl_order['id'],
            'tp1_order_id': tp1_order['id'],
            'tp2_order_id': tp2_order['id'],
            'tp3_order_id': tp3_order['id']
        }
        save_state()

        chart_path = save_chart(get_data(pick), pick)
        msg = f"🚀 <b>FINAL BOSS TRADE V11.2-FREE</b>\n\n" \
              f"<b>Symbol:</b> {pick}\n" \
              f"<b>Entry:</b> ${entry_price:.4f}\n" \
              f"<b>Size:</b> ${BASE_TRADE_SIZE} @ {lev_used}x ISOLATED\n" \
              f"<b>SL:</b> {SL_PCT*100:.1f}% → ${sl_price}\n" \
              f"<b>TP1:</b> {TP1_PCT*100:.1f}% (50%) → ${tp1_price}\n" \
              f"<b>TP2:</b> {TP2_PCT*100:.1f}% (30%) → ${tp2_price}\n" \
              f"<b>TP3:</b> {TP3_PCT*100:.1f}% (15%) → ${tp3_price}\n" \
              f"<b>Trail:</b> {TRAIL_CALLBACK*100:.0f}% after +{TRAIL_ACTIVATE*100:.0f}%\n\n" \
              f"<b>Conf:</b> {boss_conf}% | <b>LETS GOOO! 🔥</b>"

        tg(msg, chart_path)
        logging.info(f"TRADE EXECUTED: {pick} @ {entry_price} | {lev_used}x")
        return True

    except Exception as e:
        logging.error(f"Execute error {pick}: {e}")
        tg(f"⚠️ EXECUTE FAILED\n{pick}\n{str(e)[:100]}")
        return False

# ====================== START BOT ======================
load_state()
mode = "LIVE MONEY" if IS_LIVE else "PAPER TRADE"
logging.info(f"🤖 V11.2-FREE | MODE: {mode} | Groq Restored")
tg(f"🤖 <b>V11.2-FREE GROQ RESTORED</b>\nMode: {mode}\nReady na ulit! 🔥")

while True:
    try:
        start_time = time.time()

        if not check_circuit_breaker():
            logging.info("Circuit breaker triggered. Sleeping 1 hour.")
            time.sleep(3600)
            continue

        ensure_sl_tp_exist()
        manage_positions()

        balance = exchange.fetch_balance()['USDT']['free']
        open_positions = get_open_positions()

        current_symbols = {p['symbol'] for p in open_positions}
        for sym in list(active_trades.keys()):
            if sym not in current_symbols:
                logging.info(f"Position closed: {sym}")
                del active_trades[sym]
        save_state()

        if balance < BASE_TRADE_SIZE or len(open_positions) >= MAX_OPEN:
            time.sleep(SLEEP_SEC)
            continue

        # SCANNER
        scan_prompt = f"Pick 1 strongest 30m uptrend coin from: {SYMBOLS}. Avoid: {list(current_symbols)}. Prefer BTC/ETH/BNB. Must be above EMA200. Return ONLY JSON: {{\"pick\":\"BTC/USDT\",\"reason\":\"strong trend\"}}"
        scan = ask_ai("BOSS", scan_prompt)
        pick = scan.get('pick')
        if not pick or pick in current_symbols:
            time.sleep(SLEEP_SEC)
            continue

        df = get_data(pick)
        last = df.iloc[-1]

        if pd.isna(last['ema50']) or pd.isna(last['ema200']) or pd.isna(last['rsi']) or pd.isna(last['atr']):
            time.sleep(SLEEP_SEC)
            continue

        atr_pct = (last['atr'] / last['close']) * 100
        if atr_pct > MAX_ATR_PCT or atr_pct > 2.5:
            logging.info(f"SKIP {pick} | ATR {atr_pct:.1f}% too high")
            time.sleep(SLEEP_SEC)
            continue

        if last['rsi'] > 70:
            logging.info(f"SKIP {pick} | RSI {last['rsi']:.1f} overbought")
            time.sleep(SLEEP_SEC)
            continue

        # BOSS VOTE
        trend_ok = last['close'] > last['ema200'] and last['ema50'] > last['ema200']
        lev = LEVERAGE_MAP.get(pick, DEFAULT_LEVERAGE)
        boss_prompt = f"Analyze {pick} 30m LONG. Price:{last['close']:.4f}, EMA50:{last['ema50']:.4f}, EMA200:{last['ema200']:.4f}, RSI:{last['rsi']:.1f}, ATR:{atr_pct:.1f}%. Trend OK: {trend_ok}. Return ONLY JSON: {{\"vote\":\"BUY\",\"confidence\":85,\"reason\":\"...\"}}"
        boss = ask_ai("BOSS", boss_prompt)
        if boss.get('vote') != 'BUY' or boss.get('confidence', 0) < MIN_CONFIDENCE:
            time.sleep(SLEEP_SEC)
            continue

        # HUNTER + ELDER
        hunter = ask_ai("HUNTER", f"Good aggressive LONG entry for {pick}? RSI:{last['rsi']:.1f}, ATR:{atr_pct:.1f}%, Trend up. Return ONLY JSON: {{\"valid\":true}}")
        elder = ask_ai("ELDER", f"Safe to risk ${BASE_TRADE_SIZE} on {pick} with ${balance:.2f}? Return ONLY JSON: {{\"approve\":true}}")

        if not hunter.get('valid', True) or not elder.get('approve', True):
            time.sleep(SLEEP_SEC)
            continue

        logging.info(f"✅ APPROVED → {pick} | {lev}x | Conf:{boss.get('confidence')}%")
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
