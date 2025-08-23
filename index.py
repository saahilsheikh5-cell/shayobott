import os 
import telebot
import requests
import time
import threading
import numpy as np
import pandas as pd
from flask import Flask, request
from telebot import types

# === CONFIG (use environment variable correctly) ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # get the token from Render environment
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set!")

WEBHOOK_URL = "https://shayobott.onrender.com/" + BOT_TOKEN
bot = telebot.TeleBot(BOT_TOKEN)

# Default portfolio and watchlist
portfolio = {"BTCUSDT": 0.5, "ETHUSDT": 2, "SOLUSDT": 50}
watchlist = set(portfolio.keys())
signals_on = True

BASE_URL = "https://api.binance.com/api/v3"

# === FIXED CHAT ID ===
USER_CHAT_ID = 1263295916  # your Telegram chat ID

# === HELPER FUNCTIONS ===
def fetch_price(symbol):
    try:
        r = requests.get(f"{BASE_URL}/ticker/24hr?symbol={symbol}", timeout=5).json()
        return float(r["lastPrice"]), float(r["priceChangePercent"])
    except:
        return None, None

def fetch_klines(symbol, interval="1m", limit=100):
    try:
        url = f"{BASE_URL}/klines?symbol={symbol}&interval={interval}&limit={limit}"
        data = requests.get(url, timeout=5).json()
        closes = [float(x[4]) for x in data]
        return closes
    except:
        return []

def calc_rsi(prices, period=14):
    if len(prices) < period: return None
    deltas = np.diff(prices)
    gains = deltas[deltas > 0].sum() / period
    losses = -deltas[deltas < 0].sum() / period
    if losses == 0: return 100
    rs = gains / losses
    return 100 - (100 / (1 + rs))

def calc_macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal: return None, None, None
    fast_ma = np.mean(prices[-fast:])
    slow_ma = np.mean(prices[-slow:])
    macd = fast_ma - slow_ma
    signal_line = np.mean([np.mean(prices[-(slow+i):]) for i in range(signal)])
    hist = macd - signal_line
    return macd, signal_line, hist

def generate_signal(symbol, interval):
    prices = fetch_klines(symbol, interval)
    if not prices: return None
    rsi = calc_rsi(prices)
    macd, signal_line, hist = calc_macd(prices)
    last_price = prices[-1]
    if rsi is None or macd is None: return None

    # Determine base signal by RSI
    if rsi < 30:
        base_signal = "💚 STRONG BUY"
        rsi_strength = "strong"
    elif rsi < 40:
        base_signal = "✅ BUY"
        rsi_strength = "normal"
    elif rsi > 70:
        base_signal = "💔 STRONG SELL"
        rsi_strength = "strong"
    elif rsi > 60:
        base_signal = "❌ SELL"
        rsi_strength = "normal"
    else:
        return None

    # Determine trend by MACD
    trend = ""
    macd_trend = ""
    if macd > signal_line:
        trend = " (MACD Bullish)"
        macd_trend = "bullish"
    elif macd < signal_line:
        trend = " (MACD Bearish)"
        macd_trend = "bearish"

    # Upgrade signal to VERY STRONG if both RSI and MACD confirm
    if rsi_strength == "strong":
        if (base_signal.startswith("💚") and macd_trend == "bullish") or \
           (base_signal.startswith("💔") and macd_trend == "bearish"):
            base_signal = "💎 VERY STRONG " + base_signal.split(" ")[-1]  # e.g., 💎 VERY STRONG BUY

    return f"{base_signal} — {symbol} {interval} | Price: {last_price:.2f}, RSI={rsi:.2f}{trend}"

def top_movers(limit=5):
    try:
        r = requests.get(f"{BASE_URL}/ticker/24hr", timeout=5).json()
        movers_1h = sorted(r, key=lambda x: abs(float(x["priceChangePercent"])), reverse=True)[:limit]
        movers_24h = sorted(r, key=lambda x: abs(float(x["priceChangePercent"])), reverse=True)[:limit]
        msg = "🚀 *Top Movers*\n\n⏱ *1 Hour Movers:*\n"
        for sym in movers_1h:
            msg += f"{sym['symbol']}: {float(sym['priceChangePercent']):+.2f}%\n"
        msg += "\n📅 *24 Hour Movers:*\n"
        for sym in movers_24h:
            msg += f"{sym['symbol']}: {float(sym['priceChangePercent']):+.2f}%\n"
        return msg
    except:
        return "Error fetching movers"

def get_portfolio_summary():
    total = 0
    text = "📊 *Your Portfolio:*\n\n"
    for coin, qty in portfolio.items():
        price, change = fetch_price(coin)
        if price:
            value = qty * price
            total += value
            text += f"{coin[:-4]}: {qty} × ${price:.2f} = ${value:.2f} ({change:.2f}% 24h)\n"
        else: text += f"{coin}: Error fetching price\n"
    text += f"\n💰 Total Portfolio Value: ${total:.2f}"
    return text

def get_signals_text():
    text = "📊 *Technical Analysis Signals*\n\n"
    for sym in watchlist:
        text += f"🔹 {sym}\n"
        for interval in ["1m","5m","15m","1h","4h","1d"]:
            sig = generate_signal(sym, interval)
            clean_sig = sig.split("—")[0].strip() + " | " + sig.split("|")[1].strip() if sig else "No clear signal"
            text += f"   ⏱ {interval}: {clean_sig}\n"
        text += "\n"
    return text

# === DASHBOARD ===
@bot.message_handler(commands=["start","dashboard"])
def dashboard(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Portfolio", callback_data="portfolio"),
        types.InlineKeyboardButton("📈 Live Prices", callback_data="live_prices"),
        types.InlineKeyboardButton("📊 Technical Analysis", callback_data="technical_analysis"),
        types.InlineKeyboardButton("🚀 Top Movers", callback_data="top_movers"),
        types.InlineKeyboardButton("➕ Add Coin", callback_data="add_coin"),
        types.InlineKeyboardButton("➖ Remove Coin", callback_data="remove_coin"),
        types.InlineKeyboardButton("🔔 Signals ON", callback_data="signals_on"),
        types.InlineKeyboardButton("🔕 Signals OFF", callback_data="signals_off"),
        types.InlineKeyboardButton("🔄 Refresh Dashboard", callback_data="refresh_dashboard")
    )
    bot.send_message(message.chat.id, "📌 *Crypto Dashboard*\n\nChoose an option:", reply_markup=markup, parse_mode="Markdown")

# === CALLBACK HANDLER ===
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    global signals_on
    chat_id = call.message.chat.id
    data = call.data

    if data == "portfolio":
        bot.send_message(chat_id, get_portfolio_summary(), parse_mode="Markdown")
    elif data == "technical_analysis":
        bot.send_message(chat_id, get_signals_text(), parse_mode="Markdown")
    elif data == "top_movers":
        bot.send_message(chat_id, top_movers(), parse_mode="Markdown")
    elif data == "add_coin":
        bot.send_message(chat_id, "Send coin symbol to add (e.g., MATICUSDT)")
        bot.register_next_step_handler(call.message, add_coin_step)
    elif data == "remove_coin":
        bot.send_message(chat_id, "Send coin symbol to remove")
        bot.register_next_step_handler(call.message, remove_coin_step)
    elif data == "signals_on":
        signals_on = True
        bot.send_message(chat_id, "✅ Signals are now ON")
    elif data == "signals_off":
        signals_on = False
        bot.send_message(chat_id, "❌ Signals are now OFF")
    elif data == "live_prices":
        text = ""
        for sym in watchlist:
            price, change = fetch_price(sym)
            if price: text += f"{sym}: ${price:.2f} ({change:+.2f}% 24h)\n"
        bot.send_message(chat_id, text)
    elif data == "refresh_dashboard":
        dashboard(call.message)

def add_coin_step(message):
    symbol = message.text.upper()
    watchlist.add(symbol)
    bot.send_message(message.chat.id, f"{symbol} added ✅")

def remove_coin_step(message):
    symbol = message.text.upper()
    if symbol in watchlist:
        watchlist.remove(symbol)
        bot.send_message(message.chat.id, f"{symbol} removed ❌")
    else:
        bot.send_message(message.chat.id, f"{symbol} not in watchlist")

# === BACKGROUND SIGNAL ALERTS ===
def signal_watcher():
    while True:
        if signals_on:
            for sym in watchlist:
                for interval in ["1m","5m","15m","1h","4h","1d"]:
                    sig = generate_signal(sym, interval)
                    if sig:
                        bot.send_message(USER_CHAT_ID, sig)
        time.sleep(60)

threading.Thread(target=signal_watcher, daemon=True).start()

# === FLASK WEBHOOK ===
app = Flask(__name__)

@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    update = tele
