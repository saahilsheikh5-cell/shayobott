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
auto_signal_threads = {}
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

def get_klines(symbol, interval, limit=100):
    try:
        url = f"{BINANCE_URL}?symbol={symbol}&interval={interval}&limit={limit}"
        data = requests.get(url, timeout=10).json()
        df = pd.DataFrame(data, columns=[
            "time", "o", "h", "l", "c", "v",
            "ct", "qv", "tn", "tb", "qtb", "ignore"
        ])
        df["c"] = df["c"].astype(float)
        return df
    except:
        return None

def get_rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(period).mean()
    avg_loss = pd.Series(loss).rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

def analyze(symbol, interval="1h"):
    df = get_klines(symbol, interval, 100)
    if df is None or df.empty:
        return None
    close = df["c"]
    price = close.iloc[-1]
    rsi = get_rsi(close).iloc[-1]
    macd, sig = get_macd(close)
    macd_v = macd.iloc[-1]
    sig_v = sig.iloc[-1]

    # Adjusted thresholds
    signal = "NEUTRAL"
    emoji = "⚪"
    if rsi < 30:
        signal = "STRONG BUY"
        emoji = "🔺🟢"
    elif rsi > 70:
        signal = "STRONG SELL"
        emoji = "🔻🔴"

    return {
        "price": price,
        "rsi": round(rsi, 2),
        "macd": round(macd_v, 2),
        "sig": round(sig_v, 2),
        "signal": signal,
        "emoji": emoji
    }

def get_top_movers(interval):
    data = requests.get(ALL_COINS_URL, timeout=10).json()
    df = pd.DataFrame(data)
    df["priceChangePercent"] = df["priceChangePercent"].astype(float)

    if interval in ["15m", "1h"]:
        movers = []
        symbols = df.sort_values("quoteVolume", ascending=False)["symbol"].head(50)  # top 50 by volume
        kl_interval = "15m" if interval=="15m" else "1h"
        for sym in symbols:
            k = get_klines(sym, kl_interval, 2)
            if k is not None and len(k) >= 2:
                old, new = k["c"].iloc[0], k["c"].iloc[-1]
                change = ((new - old) / old) * 100
                movers.append((sym, change))
        movers = sorted(movers, key=lambda x: x[1], reverse=True)[:10]
    else:  # 24h
        movers = df.sort_values("priceChangePercent", ascending=False).head(10)
        movers = list(zip(movers["symbol"], movers["priceChangePercent"]))
    return movers

# === MENUS ===
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📊 My Coins", "➕ Add Coin", "➖ Remove Coin")
    kb.row("🚀 Top Movers", "🤖 Auto Signals")
    return kb

def timeframe_menu(prefix, coin=None):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("1m", callback_data=f"{prefix}_{coin}_1m"),
        types.InlineKeyboardButton("5m", callback_data=f"{prefix}_{coin}_5m"),
        types.InlineKeyboardButton("15m", callback_data=f"{prefix}_{coin}_15m")
    )
    kb.row(
        types.InlineKeyboardButton("1h", callback_data=f"{prefix}_{coin}_1h"),
        types.InlineKeyboardButton("1d", callback_data=f"{prefix}_{coin}_1d")
    )
    kb.row(types.InlineKeyboardButton("🔙 Back", callback_data="back_main"))
    return kb

def movers_menu():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("15m", callback_data="movers_15m"),
        types.InlineKeyboardButton("1h", callback_data="movers_1h"),
        types.InlineKeyboardButton("24h", callback_data="movers_24h")
    )
    kb.row(types.InlineKeyboardButton("🔙 Back", callback_data="back_main"))
    return kb

def coins_list_menu(prefix):
    coins = load_coins()
    kb = types.InlineKeyboardMarkup()
    for coin in coins:
        kb.row(types.InlineKeyboardButton(coin, callback_data=f"{prefix}_{coin}"))
    kb.row(types.InlineKeyboardButton("🔙 Back", callback_data="back_main"))
    return kb

# === HANDLERS ===
@bot.message_handler(commands=["start"])
def start(msg):
    bot.send_message(msg.chat.id, "Welcome to SaahilCryptoBot 🚀", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📊 My Coins")
def my_coins(msg):
    coins = load_coins()
    if not coins:
        bot.send_message(msg.chat.id, "No coins added yet. Use ➕ Add Coin first.")
        return
    bot.send_message(msg.chat.id, "Select a coin for technical analysis:", reply_markup=coins_list_menu("tech"))

@bot.message_handler(func=lambda m: m.text == "➕ Add Coin")
def add_coin(msg):
    bot.send_message(msg.chat.id, "Type the coin symbol to add (e.g., BTCUSDT):")
    bot.register_next_step_handler(msg, save_coin)

def save_coin(msg):
    coin = msg.text.strip().upper()
    coins = load_coins()
    if coin in coins:
        bot.send_message(msg.chat.id, f"{coin} is already in your list.")
        return
    coins.append(coin)
    save_coins(coins)
    bot.send_message(msg.chat.id, f"{coin} added successfully.", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "➖ Remove Coin")
def remove_coin(msg):
    coins = load_coins()
    if not coins:
        bot.send_message(msg.chat.id, "No coins to remove.")
        return
    bot.send_message(msg.chat.id, "Select a coin to remove:", reply_markup=coins_list_menu("remove"))

@bot.message_handler(func=lambda m: m.text == "🚀 Top Movers")
def top_movers(msg):
    bot.send_message(msg.chat.id, "Select timeframe:", reply_markup=movers_menu())

@bot.message_handler(func=lambda m: m.text == "🤖 Auto Signals")
def auto_signals(msg):
    bot.send_message(msg.chat.id, "Select timeframe for auto signals:", reply_markup=timeframe_menu("auto"))

# === CALLBACK HANDLER ===
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(call):
    data = call.data
    if data == "back_main":
        bot.send_message(call.message.chat.id, "Back to main menu", reply_markup=main_menu())

    # Show timeframe menu for a coin
    elif data.startswith("tech_") and len(data.split("_"))==2:
        coin = data.split("_")[1]
        bot.send_message(call.message.chat.id, f"Select timeframe for {coin}:", reply_markup=timeframe_menu("tech", coin))

    # Technical Analysis for coin + timeframe
    elif data.startswith("tech_") and len(data.split("_"))==3:
        _, coin, tf = data.split("_")
        result = analyze(coin, tf)
        if result:
            bot.send_message(
                call.message.chat.id,
                f"[{tf}] {coin}\nPrice: {result['price']}\nRSI: {result['rsi']}\nMACD: {result['macd']}\nSignal: {result['signal']} {result['emoji']}"
            )
        else:
            bot.send_message(call.message.chat.id, f"Failed to fetch data for {coin}.")

    # Remove Coin
    elif data.startswith("remove_"):
        _, coin = data.split("_")
        coins = load_coins()
        if coin in coins:
            coins.remove(coin)
            save_coins(coins)
        bot.send_message(call.message.chat.id, f"{coin} removed.", reply_markup=main_menu())

    # Top Movers
    elif data.startswith("movers_"):
        _, tf = data.split("_")
        movers = get_top_movers(tf)
        text = f"📈 Top Movers ({tf})\n\n"
        for sym, chg in movers:
            text += f"{sym}: 🟢 {round(chg,2)}%\n"
        bot.send_message(call.message.chat.id, text)

    # Auto Signals
    elif data.startswith("auto_"):
        _, tf, coin = None, None, None
        parts = data.split("_")
        if len(parts) == 2:
            tf = parts[1]
        if tf in auto_signal_threads and auto_signal_threads[tf].is_alive():
            bot.send_message(call.message.chat.id, f"Auto signals already running for {tf}.")
        else:
            t = threading.Thread(target=run_auto_signals, args=(call.message.chat.id, tf), daemon=True)
            auto_signal_threads[tf] = t
            t.start()
            bot.send_message(call.message.chat.id, f"Started auto signals for {tf} timeframe.")

# === AUTO SIGNALS FUNCTION ===
def run_auto_signals(chat_id, interval):
    last_signals = {}
    sleep_time = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}.get(interval, 60)
    while True:
        coins = load_coins()
        for coin in coins:
            result = analyze(coin, interval)
            if result:
                if last_signals.get(coin) != result['signal']:
                    bot.send_message(
                        chat_id,
                        f"[{interval}] {coin}\nPrice: {result['price']}\nRSI: {result['rsi']}\nMACD: {result['macd']}\nSignal: {result['signal']} {result['emoji']}"
                    )
                    last_signals[coin] = result['signal']
        time.sleep(sleep_time)

# === WEBHOOK ===
@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route("/")
def index():
    return "Bot running!"

# === RUN ===
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

