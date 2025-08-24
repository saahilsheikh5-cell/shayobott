import os
import json
import telebot
import requests
import pandas as pd
import numpy as np
import time
import threading
from flask import Flask, request
from telebot import types

# === CONFIG ===
BOT_TOKEN = "7638935379:AAEmLD7JHLZ36Ywh5tvmlP1F8xzrcNrym_Q"
WEBHOOK_URL = "https://shayobott-2.onrender.com/" + BOT_TOKEN
BINANCE_URL = "https://api.binance.com/api/v3/klines"
ALL_COINS_URL = "https://api.binance.com/api/v3/ticker/24hr"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# === STORAGE ===
COINS_FILE = "coins.json"
auto_signal_cooldown = {}  # per coin cooldown to avoid spam
lock = threading.Lock()

# === HELPER FUNCTIONS ===
def load_coins():
    if not os.path.exists(COINS_FILE):
        with open(COINS_FILE, "w") as f:
            json.dump([], f)
    with open(COINS_FILE, "r") as f:
        return json.load(f)

def save_coins(coins):
    with open(COINS_FILE, "w") as f:
        json.dump(coins, f)

def get_coin_name(symbol):
    for quote in ["USDT","BTC","BNB","ETH","EUR","BRL","GBP"]:
        if symbol.endswith(quote):
            return symbol.replace(quote,"")
    return symbol

def get_klines(symbol, interval, limit=100):
    try:
        url = f"{BINANCE_URL}?symbol={symbol}&interval={interval}&limit={limit}"
        data = requests.get(url, timeout=10).json()
        df = pd.DataFrame(data, columns=["time", "o", "h", "l", "c", "v", "ct", "qv", "tn", "tb", "qtb", "ignore"])
        df['c'] = df['c'].astype(float)
        return df
    except:
        return None

def get_sma(series, period=20):
    return series.rolling(period).mean()

def get_ema(series, period=20):
    return series.ewm(span=period, adjust=False).mean()

def get_rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta>0, delta,0)
    loss = np.where(delta<0, -delta,0)
    avg_gain = pd.Series(gain).rolling(period).mean()
    avg_loss = pd.Series(loss).rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# === ANALYSIS FUNCTIONS ===
def analyze_my_coin(symbol, interval="1h"):
    df = get_klines(symbol, interval, 100)
    if df is None or df.empty:
        return None
    close = df["c"]
    price = close.iloc[-1]
    sma20 = get_sma(close,20).iloc[-1]
    ema20 = get_ema(close,20).iloc[-1]
    rsi = get_rsi(close).iloc[-1]

    if rsi < 30:
        signal = "Buy"
        emoji = "🟢"
        explanation = f"Price near support, RSI {round(rsi,2)} indicates oversold conditions."
    elif rsi > 70:
        signal = "Sell"
        emoji = "🔴"
        explanation = f"Price near resistance, RSI {round(rsi,2)} indicates overbought conditions."
    else:
        signal = "Neutral"
        emoji = "⚪"
        explanation = f"Price near SMA20({round(sma20,2)}) and EMA20({round(ema20,2)}), RSI {round(rsi,2)} suggests no strong momentum."

    return {"price": round(price,2),"signal": signal,"emoji": emoji,"explanation": explanation}

def analyze_strong_signal(symbol):
    df = get_klines(symbol, "15m", 50)  # scan 15m candles
    if df is None or df.empty:
        return None
    close = df['c']
    price = close.iloc[-1]
    rsi = get_rsi(close).iloc[-1]

    # ultra strong thresholds
    if rsi < 15:
        signal = "Strong Buy"
        emoji = "🔺🟢"
        stop_loss = round(price*0.97, 5)
        take_profit = round(price*1.03,5)
        valid_for = "5m"
    elif rsi > 85:
        signal = "Strong Sell"
        emoji = "🔻🔴"
        stop_loss = round(price*1.03,5)
        take_profit = round(price*0.97,5)
        valid_for = "5m"
    else:
        return None

    return {"price": round(price,5),"signal": signal,"emoji": emoji,"stop_loss": stop_loss,"take_profit": take_profit,"valid_for": valid_for}

def get_top_movers():
    data = requests.get(ALL_COINS_URL, timeout=10).json()
    df = pd.DataFrame(data)
    df['priceChangePercent'] = df['priceChangePercent'].astype(float)
    movers = df.sort_values('priceChangePercent',ascending=False).head(10)
    movers = [(get_coin_name(s), round(c,2)) for s,c in zip(movers['symbol'], movers['priceChangePercent'])]
    return movers

# === MENUS ===
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📊 My Coins","➕ Add Coin","➖ Remove Coin")
    kb.row("🚀 Top Movers","🤖 Auto Signals")
    return kb

def coins_list_menu(prefix):
    coins = load_coins()
    kb = types.InlineKeyboardMarkup()
    for coin in coins:
        kb.row(types.InlineKeyboardButton(get_coin_name(coin), callback_data=f"{prefix}_{coin}"))
    kb.row(types.InlineKeyboardButton("🔙 Back", callback_data="back_main"))
    return kb

# === CALLBACK HANDLER ===
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(call):
    data = call.data
    if data=="back_main":
        bot.send_message(call.message.chat.id,"Back to main menu", reply_markup=main_menu())
        return
    elif data.startswith("tech_"):
        coin = data.split("_")[1]
        result = analyze_my_coin(coin)
        if result:
            text = f"🔎 Technical Analysis for {get_coin_name(coin)}:\n"
            for tf in ['1m','5m','15m','1h','1d']:
                res_tf = analyze_my_coin(coin,tf)
                if res_tf:
                    text += f"⏰ {tf}: {res_tf['emoji']} {res_tf['signal']} (Price ${res_tf['price']})\n"
            bot.send_message(call.message.chat.id,text)
        else:
            bot.send_message(call.message.chat.id,f"Failed to fetch data for {get_coin_name(coin)}.")
        return

# === AUTO SIGNALS ===
def run_auto_signals(chat_id):
    while True:
        data = requests.get(ALL_COINS_URL, timeout=10).json()
        for coin_data in data:
            sym = coin_data['symbol']
            result = analyze_strong_signal(sym)
            if result:
                with lock:
                    last = auto_signal_cooldown.get(sym,0)
                    if time.time() - last > 300:  # 5 min cooldown per coin
                        text = f"🪙 {get_coin_name(sym)} | ${result['price']}\n{result['emoji']} {result['signal']}\nStop Loss: ${result['stop_loss']} | Take Profit: ${result['take_profit']}\nValid for: {result['valid_for']}"
                        bot.send_message(chat_id,text)
                        auto_signal_cooldown[sym] = time.time()
        time.sleep(60)

# === MESSAGE HANDLERS ===
@bot.message_handler(commands=["start"])
def start(msg):
    bot.send_message(msg.chat.id,"Welcome to SaahilCryptoBot 🚀", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text=="📊 My Coins")
def my_coins(msg):
    coins = load_coins()
    if not coins:
        bot.send_message(msg.chat.id,"No coins added yet. Use ➕ Add Coin first.")
        return
    bot.send_message(msg.chat.id,"Select a coin:", reply_markup=coins_list_menu("tech"))

@bot.message_handler(func=lambda m: m.text=="➕ Add Coin")
def add_coin(msg):
    bot.send_message(msg.chat.id,"Type the coin symbol to add (e.g., BTCUSDT):")
    bot.register_next_step_handler(msg, save_coin)

def save_coin(msg):
    coin = msg.text.strip().upper()
    coins = load_coins()
    if coin not in coins:
        coins.append(coin)
        save_coins(coins)
    bot.send_message(msg.chat.id,f"{get_coin_name(coin)} added successfully.", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text=="➖ Remove Coin")
def remove_coin(msg):
    coins = load_coins()
    if not coins:
        bot.send_message(msg.chat.id,"No coins to remove.")
        return
    bot.send_message(msg.chat.id,"Select a coin to remove:", reply_markup=coins_list_menu("remove"))

@bot.message_handler(func=lambda m: m.text=="🚀 Top Movers")
def top_movers(msg):
    movers = get_top_movers()
    text = "📈 Top Movers (15m):\n"
    for sym,chg in movers:
        arrow = "🟢" if chg>=0 else "🔴"
        text += f"{sym}: {arrow} {chg}%\n"
    bot.send_message(msg.chat.id,text)

@bot.message_handler(func=lambda m: m.text=="🤖 Auto Signals")
def auto_signals(msg):
    bot.send_message(msg.chat.id,"Started auto signals for all coins (Strong Buy/Sell).")
    t = threading.Thread(target=run_auto_signals, args=(msg.chat.id,), daemon=True)
    t.start()

@bot.message_handler(commands=["analyse"])
def analyse_any(msg):
    parts = msg.text.split()
    if len(parts)<2:
        bot.send_message(msg.chat.id,"Usage: /analyse SYMBOL")
        return
    sym = parts[1].upper()
    result = analyze_my_coin(sym)
    if result:
        text = f"🔎 Technical Analysis for {get_coin_name(sym)}:\n"
        for tf in ['1m','5m','15m','1h','1d']:
            res_tf = analyze_my_coin(sym,tf)
            if res_tf:
                text += f"⏰ {tf}: {res_tf['emoji']} {res_tf['signal']} (Price ${res_tf['price']})\n"
        bot.send_message(msg.chat.id,text)
    else:
        bot.send_message(msg.chat.id,f"Failed to fetch data for {get_coin_name(sym)}.")

# === WEBHOOK ===
@app.route('/'+BOT_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode('utf-8'))])
    return '!',200

@app.route('/')
def index():
    return 'Bot running!'

# === RUN ===
if __name__=="__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)))




