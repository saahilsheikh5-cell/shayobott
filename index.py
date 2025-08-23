import os
import time
import threading
import requests
import numpy as np
import pandas as pd
from flask import Flask, request
import telebot
from telebot import types

# === CONFIG ===
BOT_TOKEN = "7638935379:AAEmLD7JHLZ36Ywh5tvmlP1F8xzrcNrym_Q"
WEBHOOK_URL = "https://shayobott-2.onrender.com/" + BOT_TOKEN
CHAT_ID = 1263295916  # for auto-sent signals

bot = telebot.TeleBot(BOT_TOKEN)

# Default portfolio and watchlist
portfolio = {"BTCUSDT": 0.5, "ETHUSDT": 2, "SOLUSDT": 50, "XRPUSDT": 100, "AAVEUSDT": 20}
watchlist = set(portfolio.keys())
signals_on = True
auto_interval = 60  # default auto-signal interval in seconds

BASE_URL = "https://api.binance.com/api/v3"

# === HELPER FUNCTIONS ===
def fetch_price(symbol):
    try:
        r = requests.get(f"{BASE_URL}/ticker/price?symbol={symbol}", timeout=5).json()
        return float(r["price"])
    except:
        return None

def fetch_klines(symbol, interval="1m", limit=100):
    try:
        data = requests.get(f"{BASE_URL}/klines?symbol={symbol}&interval={interval}&limit={limit}", timeout=5).json()
        return [float(x[4]) for x in data]
    except:
        return []

def calc_rsi(prices, period=14):
    if len(prices) < period: return None
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal: return None, None, None
    fast_ma = np.mean(prices[-fast:])
    slow_ma = np.mean(prices[-slow:])
    macd_val = fast_ma - slow_ma
    signal_line = np.mean([np.mean(prices[-(slow+i):-i] if i != 0 else prices[-slow:]) for i in range(signal)])
    hist = macd_val - signal_line
    return macd_val, signal_line, hist

def generate_signal(symbol, interval):
    prices = fetch_klines(symbol, interval)
    if not prices: return None
    rsi = calc_rsi(prices)
    macd, signal_line, hist = calc_macd(prices)
    last_price = prices[-1]
    if rsi is None or macd is None: return None

    # Strong vs normal signals
    if rsi < 20: base_signal = "💚 STRONG BUY"
    elif rsi < 40: base_signal = "✅ BUY"
    elif rsi > 80: base_signal = "💔 STRONG SELL"
    elif rsi > 60: base_signal = "❌ SELL"
    else: return None

    trend = ""
    if macd > signal_line: trend = " (MACD Bullish)"
    elif macd < signal_line: trend = " (MACD Bearish)"

    # Targets and stop-loss
    stop_loss = last_price * 0.98 if "BUY" in base_signal else last_price * 1.02
    targets = [last_price * 1.02, last_price * 1.05, last_price * 1.08] if "BUY" in base_signal else [last_price * 0.98, last_price * 0.95, last_price * 0.92]

    return f"{base_signal} — {symbol} {interval} | Price: {last_price:.2f}{trend}\nTargets: {', '.join(f'{t:.2f}' for t in targets)} | Stop-loss: {stop_loss:.2f}"

def top_movers(limit=5):
    try:
        data = requests.get(f"{BASE_URL}/ticker/24hr", timeout=5).json()
        movers_5m = sorted(data, key=lambda x: abs(float(x.get("priceChangePercent",0))), reverse=True)[:limit]
        movers_1h = sorted(data, key=lambda x: abs(float(x.get("priceChangePercent",0))), reverse=True)[:limit]
        movers_24h = sorted(data, key=lambda x: abs(float(x.get("priceChangePercent",0))), reverse=True)[:limit]

        msg = "🚀 *Top Movers*\n\n⏱ *5 Min Movers:*\n"
        for sym in movers_5m: msg += f"{sym['symbol']}: {float(sym['priceChangePercent']):+.2f}%\n"
        msg += "\n⏱ *1 Hour Movers:*\n"
        for sym in movers_1h: msg += f"{sym['symbol']}: {float(sym['priceChangePercent']):+.2f}%\n"
        msg += "\n⏱ *24 Hour Movers:*\n"
        for sym in movers_24h: msg += f"{sym['symbol']}: {float(sym['priceChangePercent']):+.2f}%\n"
        return msg
    except:
        return "Error fetching movers"

def get_portfolio_summary():
    total = 0
    text = "📊 *Your Portfolio:*\n\n"
    for coin, qty in portfolio.items():
        price = fetch_price(coin)
        if price:
            value = qty * price
            total += value
            text += f"{coin}: {qty} × ${price:.2f} = ${value:.2f}\n"
        else:
            text += f"{coin}: Error fetching price\n"
    text += f"\n💰 Total Portfolio Value: ${total:.2f}"
    return text

def get_signals_text():
    text = "📊 *Technical Signals*\n\n"
    for sym in watchlist:
        text += f"🔹 {sym}\n"
        for interval in ["1m","5m","15m","1h","4h","1d"]:
            sig = generate_signal(sym, interval)
            text += f"   ⏱ {interval}: {sig if sig else 'No clear signal'}\n"
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
            price = fetch_price(sym)
            text += f"{sym}: ${price:.2f}\n" if price else f"{sym}: Error fetching price\n"
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

# === AUTO-SIGNAL THREAD ===
def auto_signal_watcher():
    while True:
        if signals_on:
            for sym in watchlist:
                for interval in ["1

