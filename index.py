import os
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
PRICE_URL = "https://api.binance.com/api/v3/ticker/price"
ALL_COINS_URL = "https://api.binance.com/api/v3/ticker/24hr"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# === STORAGE ===
user_coins = {}
user_auto_signals = {}
lock = threading.Lock()

# === HELPERS ===
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

    signal = "NEUTRAL"
    emoji = "⚪"
    if rsi < 35 and macd_v > sig_v:
        signal = "STRONG BUY"
        emoji = "🔺🟢"
    elif rsi > 65 and macd_v < sig_v:
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

    # Use 5m/1h/24h equivalent
    if interval == "5m":
        movers = []
        for sym in df["symbol"].unique():
            k = get_klines(sym, "5m", 2)
            if k is not None and len(k) >= 2:
                old, new = k["c"].iloc[0], k["c"].iloc[-1]
                change = ((new - old) / old) * 100
                movers.append((sym, change))
        movers = sorted(movers, key=lambda x: x[1], reverse=True)[:10]
    elif interval == "1h":
        movers = df.sort_values("priceChangePercent", ascending=False).head(10)
        movers = list(zip(movers["symbol"], movers["priceChangePercent"]))
    else:  # 24h
        movers = df.sort_values("priceChangePercent", ascending=False).head(10)
        movers = list(zip(movers["symbol"], movers["priceChangePercent"]))

    return movers

# === BOT MENUS ===
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ Add Coin", "📊 My Coins")
    kb.row("📈 Technical Signals", "🤖 Auto Signals")
    kb.row("🚀 Top Movers")
    return kb

def timeframe_menu(back_to):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("1m", callback_data=f"{back_to}_1m"),
        types.InlineKeyboardButton("5m", callback_data=f"{back_to}_5m"),
        types.InlineKeyboardButton("15m", callback_data=f"{back_to}_15m")
    )
    kb.row(
        types.InlineKeyboardButton("1h", callback_data=f"{back_to}_1h"),
        types.InlineKeyboardButton("1d", callback_data=f"{back_to}_1d")
    )
    kb.row(types.InlineKeyboardButton("🔙 Back", callback_data="back_main"))
    return kb

def movers_menu():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("⏱ 5m", callback_data="movers_5m"),
        types.InlineKeyboardButton("⏱ 1h", callback_data="movers_1h"),
        types.InlineKeyboardButton("⏱ 24h", callback_data="movers_24h")
    )
    kb.row(types.InlineKeyboardButton("🔙 Back", callback_data="back_main"))
    return kb

# === HANDLERS ===
@bot.message_handler(commands=["start"])
def start(msg):
    bot.send_message(msg.chat.id, "Welcome to SaahilCryptoBot 🚀", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "🚀 Top Movers")
def movers(msg):
    bot.send_message(msg.chat.id, "Select timeframe:", reply_markup=movers_menu())

@bot.callback_query_handler(func=lambda c: c.data.startswith("movers"))
def cb_movers(call):
    tf = call.data.split("_")[1]
    movers = get_top_movers(tf)
    text = f"📈 Top Movers ({tf})\n\n"
    for sym, chg in movers:
        text += f"   {sym}: 🟢 {round(chg,2)}%\n"
    bot.send_message(call.message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "📈 Technical Signals")
def tech(msg):
    bot.send_message(msg.chat.id, "Choose timeframe:", reply_markup=timeframe_menu("tech"))

@bot.message_handler(func=lambda m: m.text == "🤖 Auto Signals")
def auto(msg):
    bot.send_message(msg.chat.id, "Choose auto-signal timeframe:", reply_markup=timeframe_menu("auto"))

@bot.callback_query_handler(func=lambda c: c.data == "back_main")
def cb_back(call):
    bot.send_message(call.message.chat.id, "Back to main menu", reply_markup=main_menu())

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








