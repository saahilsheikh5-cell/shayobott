import os
import telebot
import requests
import time
import threading
import numpy as np
from flask import Flask, request
from telebot import types

# === CONFIG ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing!")

WEBHOOK_URL = "https://shayobott.onrender.com/" + BOT_TOKEN
USER_CHAT_ID = 1263295916

bot = telebot.TeleBot(BOT_TOKEN)

portfolio = {"BTCUSDT": 0.5, "ETHUSDT": 2, "SOLUSDT": 50}
watchlist = set(portfolio.keys())
signals_on = True
BASE_URL = "https://api.binance.com/api/v3"

# === HELPER FUNCTIONS ===
def fetch_price(symbol):
    try:
        r = requests.get(f"{BASE_URL}/ticker/24hr?symbol={symbol}", timeout=5).json()
        return float(r["lastPrice"]), float(r["priceChangePercent"])
    except:
        return None, None

def fetch_klines(symbol, interval="1m", limit=100):
    try:
        data = requests.get(f"{BASE_URL}/klines?symbol={symbol}&interval={interval}&limit={limit}", timeout=5).json()
        return [float(x[4]) for x in data]
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
    return macd, signal_line, macd - signal_line

def generate_signal(symbol, interval):
    prices = fetch_klines(symbol, interval)
    if not prices: return None
    rsi = calc_rsi(prices)
    macd, signal_line, hist = calc_macd(prices)
    last_price = prices[-1]
    if rsi is None or macd is None: return None

    # Base signal
    if rsi < 30: base = "💚 STRONG BUY"; rsi_strong=True
    elif rsi < 40: base = "✅ BUY"; rsi_strong=False
    elif rsi > 70: base = "💔 STRONG SELL"; rsi_strong=True
    elif rsi > 60: base = "❌ SELL"; rsi_strong=False
    else: return None

    trend=""
    macd_trend=""
    if macd > signal_line: trend=" (MACD Bullish)"; macd_trend="bullish"
    elif macd < signal_line: trend=" (MACD Bearish)"; macd_trend="bearish"

    # VERY STRONG if RSI + MACD confirm
    if rsi_strong and ((base.startswith("💚") and macd_trend=="bullish") or (base.startswith("💔") and macd_trend=="bearish")):
        base = "💎 VERY STRONG " + base.split(" ")[-1]

    return f"{base} — {symbol} {interval} | Price: {last_price:.2f}, RSI={rsi:.2f}{trend}"

def top_movers(limit=5):
    try:
        r = requests.get(f"{BASE_URL}/ticker/24hr", timeout=5).json()
        movers = sorted(r, key=lambda x: abs(float(x["priceChangePercent"])), reverse=True)[:limit]
        msg="🚀 *Top Movers*\n"
        for sym in movers:
            msg += f"{sym['symbol']}: {float(sym['priceChangePercent']):+.2f}%\n"
        return msg
    except:
        return "Error fetching movers"

def get_portfolio_summary():
    total = 0
    txt="📊 *Portfolio:*\n"
    for coin, qty in portfolio.items():
        price, change = fetch_price(coin)
        if price:
            value = qty*price
            total += value
            txt+=f"{coin[:-4]}: {qty} × ${price:.2f} = ${value:.2f} ({change:.2f}% 24h)\n"
        else: txt+=f"{coin}: Error fetching price\n"
    txt+=f"\n💰 Total: ${total:.2f}"
    return txt

def get_signals_text():
    txt="📊 *Technical Signals*\n"
    for sym in watchlist:
        txt+=f"🔹 {sym}\n"
        for interval in ["1m","5m","15m","1h","4h","1d"]:
            sig = generate_signal(sym, interval)
            txt += f"   ⏱ {interval}: {sig if sig else 'No clear signal'}\n"
        txt+="\n"
    return txt

# === DASHBOARD ===
@bot.message_handler(commands=["start","dashboard"])
def dashboard(message):
    markup=types.InlineKeyboardMarkup(row_width=2)
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
    bot.send_message(message.chat.id, "📌 *Crypto Dashboard*\nChoose an option:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    global signals_on
    chat_id = call.message.chat.id
    data = call.data

    if data=="portfolio": bot.send_message(chat_id,get_portfolio_summary(),parse_mode="Markdown")
    elif data=="technical_analysis": bot.send_message(chat_id,get_signals_text(),parse_mode="Markdown")
    elif data=="top_movers": bot.send_message(chat_id,top_movers(),parse_mode="Markdown")
    elif data=="add_coin":
        bot.send_message(chat_id,"Send coin symbol to add")
        bot.register_next_step_handler(call.message, add_coin_step)
    elif data=="remove_coin":
        bot.send_message(chat_id,"Send coin symbol to remove")
        bot.register_next_step_handler(call.message, remove_coin_step)
    elif data=="signals_on": signals_on=True; bot.send_message(chat_id,"✅ Signals ON")
    elif data=="signals_off": signals_on=False; bot.send_message(chat_id,"❌ Signals OFF")
    elif data=="live_prices":
        txt=""
        for sym in watchlist:
            price, change=fetch_price(sym)
            if price: txt+=f"{sym}: ${price:.2f} ({change:+.2f}% 24h)\n"
        bot.send_message(chat_id,txt)
    elif data=="refresh_dashboard": dashboard(call.message)

def add_coin_step(message):
    symbol=message.text.upper()
    watchlist.add(symbol)
    bot.send_message(message.chat.id,f"{symbol} added ✅")

def remove_coin_step(message):
    symbol=message.text.upper()
    if symbol in watchlist: watchlist.remove(symbol); bot.send_message(message.chat.id,f"{symbol} removed ❌")
    else: bot.send_message(message.chat.id,f"{symbol} not in watchlist")

# === SIGNALS BACKGROUND THREAD ===
def signal_watcher():
    while True:
        try:
            if signals_on:
                for sym in watchlist:
                    for interval in ["1m","5m","15m","1h","4h","1d"]:
                        sig=generate_signal(sym,interval)
                        if sig: bot.send_message(USER_CHAT_ID,sig)
        except Exception as e:
            print("Signal watcher error:", e)
        time.sleep(60)

threading.Thread(target=signal_watcher,daemon=True).start()

# === FLASK WEBHOOK ===
app=Flask(__name__)

@app.route("/"+BOT_TOKEN,methods=["POST"])
def webhook():
    update=telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "!",200

@app.route("/")
def index(): return "Bot is running!",200

if __name__=="__main__":
    try:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL)
        print("Webhook set successfully")
    except Exception as e:
        print("Webhook setup error:", e)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
