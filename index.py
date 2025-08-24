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
auto_signal_thread = None
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

def get_klines(symbol, interval="1m", limit=100):
    try:
        url = f"{BINANCE_URL}?symbol={symbol}&interval={interval}&limit={limit}"
        data = requests.get(url, timeout=10).json()
        df = pd.DataFrame(data, columns=[
            "time","o","h","l","c","v","ct","qv","tn","tb","qtb","ignore"
        ])
        df["c"] = df["c"].astype(float)
        df["h"] = df["h"].astype(float)
        df["l"] = df["l"].astype(float)
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

# === ANALYSIS ===
def analyze_coin(symbol):
    df = get_klines(symbol, "1m", 50)
    if df is None or df.empty:
        return None
    close = df["c"]
    high = df["h"].iloc[-1]
    low = df["l"].iloc[-1]
    price = close.iloc[-1]
    sma = get_sma(close,20).iloc[-1]
    ema = get_ema(close,20).iloc[-1]
    rsi = get_rsi(close,14).iloc[-1]

    # Ultra strict criteria
    if rsi <= 15 and price > sma and price > ema:
        signal = "Strong Buy"
        emoji = "🔺🟢"
    elif rsi >= 85 and price < sma and price < ema:
        signal = "Strong Sell"
        emoji = "🔻🔴"
    else:
        return None

    stop_loss = round(low if signal=="Strong Buy" else high,5)
    take_profit = round(price + (price-stop_loss)*2 if signal=="Strong Buy" else price - (stop_loss-price)*2,5)
    validity = "5m"

    return {
        "symbol": get_coin_name(symbol),
        "price": price,
        "signal": signal,
        "emoji": emoji,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "validity": validity
    }

def get_top_movers():
    data = requests.get(ALL_COINS_URL, timeout=10).json()
    df = pd.DataFrame(data)
    df["priceChangePercent"] = df["priceChangePercent"].astype(float)
    movers = df.sort_values("priceChangePercent", ascending=False).head(10)
    movers_list = [(get_coin_name(s), round(c,2)) for s,c in zip(movers["symbol"], movers["priceChangePercent"])]
    return movers_list

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
        df = get_klines(coin,"1m",50)
        if df is None:
            bot.send_message(call.message.chat.id,f"Failed to fetch data for {get_coin_name(coin)}.")
            return
        analysis_text = ""
        intervals = ["1m","5m","15m","1h","1d"]
        for tf in intervals:
            df_tf = get_klines(coin,tf,50)
            close = df_tf["c"]
            price = close.iloc[-1]
            rsi = get_rsi(close).iloc[-1]
            if rsi < 30:
                sig = "Buy 🟢"
            elif rsi>70:
                sig = "Sell 🔴"
            else:
                sig = "Neutral ⚪"
            analysis_text += f"⏰ {tf}: {sig} (Price ${round(price,2)})\n"
        bot.send_message(call.message.chat.id,f"🔎 Technical Analysis for {get_coin_name(coin)}:\n\n{analysis_text}")
        return
    elif data.startswith("remove_"):
        coin = data.split("_")[1]
        coins = load_coins()
        if coin in coins:
            coins.remove(coin)
            save_coins(coins)
        bot.send_message(call.message.chat.id,f"{get_coin_name(coin)} removed.", reply_markup=main_menu())
        return

# === AUTO SIGNALS ===
def run_auto_signals(chat_id):
    global auto_signal_thread
    last_signals = {}
    while True:
        data = requests.get(ALL_COINS_URL, timeout=10).json()
        signals = []
        for coin_data in data:
            sym = coin_data["symbol"]
            res = analyze_coin(sym)
            if res:
                key = res["symbol"]
                if last_signals.get(key)!=res["signal"]:
                    signals.append(res)
                    last_signals[key]=res["signal"]
        # send only top 10 strongest signals
        for s in sorted(signals, key=lambda x: x["signal"]=="Strong Buy", reverse=True)[:10]:
            msg = f"🪙 {s['symbol']} | ${round(s['price'],5)}\n{s['emoji']} {s['signal']}\nStop Loss: ${s['stop_loss']} | Take Profit: ${s['take_profit']}\nValid for: {s['validity']}"
            bot.send_message(chat_id,msg)
        time.sleep(60)

# === COMMANDS ===
@bot.message_handler(commands=["start"])
def start(msg):
    bot.send_message(msg.chat.id,"Welcome to SaahilCryptoBot 🚀", reply_markup=main_menu())

@bot.message_handler(commands=["analyse"])
def analyse(msg):
    parts = msg.text.split()
    if len(parts)!=2:
        bot.send_message(msg.chat.id,"Usage: /analyse SYMBOL (e.g., /analyse BTCUSDT)")
        return
    coin = parts[1].upper()
    df = get_klines(coin,"1m",50)
    if df is None:
        bot.send_message(msg.chat.id,f"Failed to fetch data for {coin}.")
        return
    analysis_text = ""
    intervals = ["1m","5m","15m","1h","1d"]
    for tf in intervals:
        df_tf = get_klines(coin,tf,50)
        close = df_tf["c"]
        price = close.iloc[-1]
        rsi = get_rsi(close).iloc[-1]
        if rsi < 30:
            sig = "Buy 🟢"
        elif rsi>70:
            sig = "Sell 🔴"
        else:
            sig = "Neutral ⚪"
        analysis_text += f"⏰ {tf}: {sig} (Price ${round(price,2)})\n"
    bot.send_message(msg.chat.id,f"🔎 Technical Analysis for {get_coin_name(coin)}:\n\n{analysis_text}")

@bot.message_handler(func=lambda m: m.text=="📊 My Coins")
def my_coins(msg):
    coins = load_coins()
    if not coins:
        bot.send_message(msg.chat.id,"No coins added yet. Use ➕ Add Coin first.")
        return
    bot.send_message(msg.chat.id,"Select a coin for technical analysis:", reply_markup=coins_list_menu("tech"))

@bot.message_handler(func=lambda m: m.text=="➕ Add Coin")
def add_coin(msg):
    bot.send_message(msg.chat.id,"Type the coin symbol to add (e.g., BTCUSDT):")
    bot.register_next_step_handler(msg, save_coin)

def save_coin(msg):
    coin = msg.text.strip().upper()
    coins = load_coins()
    if coin in coins:
        bot.send_message(msg.chat.id,f"{get_coin_name(coin)} is already in your list.")
        return
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
    text = "📈 Top Movers:\n\n"
    for sym,ch in movers:
        arrow = "🟢" if ch>=0 else "🔴"
        text += f"{sym}: {arrow} {ch}%\n"
    bot.send_message(msg.chat.id,text)

@bot.message_handler(func=lambda m: m.text=="🤖 Auto Signals")
def auto_signals(msg):
    global auto_signal_thread
    if auto_signal_thread is None or not auto_signal_thread.is_alive():
        auto_signal_thread = threading.Thread(target=run_auto_signals,args=(msg.chat.id,),daemon=True)
        auto_signal_thread.start()
        bot.send_message(msg.chat.id,"Started ultra-filtered auto signals for all coins (Strong Buy/Sell).")
    else:
        bot.send_message(msg.chat.id,"Auto signals already running.")

# === WEBHOOK ===
@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!",200

@app.route("/")
def index():
    return "Bot running!"

# === RUN ===
if __name__=="__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))





