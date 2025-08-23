import os
import time
import threading
import requests
import pandas as pd
import numpy as np
from flask import Flask, request
import telebot
from telebot import types

# === CONFIG ===
BOT_TOKEN = "7638935379:AAEmLD7JHLZ36Ywh5tvmlP1F8xzrcNrym_Q"
WEBHOOK_URL = "https://shayobott-2.onrender.com/" + BOT_TOKEN
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Default coin list (can add/remove later via buttons)
coins = []

# Default auto-update interval in seconds (can change dynamically)
update_interval = 300  # 5 minutes

# Placeholder for storing last fetched prices and signals
coin_data = {}

# === Helper Functions ===
def fetch_price(symbol):
    try:
        # Replace with real API
        response = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}")
        return float(response.json()["price"])
    except:
        return None

def fetch_movers(interval="1h"):
    try:
        # Replace with real API
        # Returns list of tuples: (symbol, percentage_change)
        return [("BTCUSDT", 2.3), ("ETHUSDT", -1.2), ("SOLUSDT", 0.8)]
    except:
        return []

def generate_signal(symbol):
    price = fetch_price(symbol)
    if price is None:
        return None
    # Example logic for signals
    macd_signal = np.random.choice(["BUY", "SELL"])
    confirmation = np.random.randint(1, 5)  # 1-5 scale
    strong = "STRONG " if confirmation == 5 else ""
    sl = round(price * 0.98, 2) if macd_signal=="BUY" else round(price*1.02,2)
    t1 = round(price*1.02,2) if macd_signal=="BUY" else round(price*0.98,2)
    t2 = round(price*1.04,2) if macd_signal=="BUY" else round(price*0.96,2)
    return f"{strong}{macd_signal} — {symbol} | Price: {price} | SL: {sl}, T1: {t1}, T2: {t2}"

def fetch_all_signals():
    results = {}
    for coin in coins:
        results[coin] = {}
        for tf in ["1m","5m","15m","1h","4h","1d"]:
            results[coin][tf] = generate_signal(coin) or "No clear signal"
    return results

def send_auto_updates():
    while True:
        if coins:
            signals = fetch_all_signals()
            for coin in coins:
                msg = f"📊 Technical Signals\n\n"
                for tf, signal in signals[coin].items():
                    msg += f"{tf}: {signal}\n"
                bot.send_message(chat_id, msg)
        time.sleep(update_interval)

# === Telegram Bot Handlers ===
@bot.message_handler(commands=["start"])
def start_handler(message):
    global chat_id
    chat_id = message.chat.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Live Prices", "Technical Signals")
    markup.row("Top Movers", "Add Coin", "Remove Coin")
    bot.send_message(chat_id, "Welcome! Use the buttons below to control the bot.", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    if message.text == "Live Prices":
        msg = "📊 Your Portfolio:\n\n"
        total = 0
        for coin in coins:
            price = fetch_price(coin)
            if price:
                total += price
                msg += f"{coin}: ${price}\n"
            else:
                msg += f"{coin}: Error fetching price\n"
        msg += f"\n💰 Total Portfolio Value: ${total:.2f}"
        bot.send_message(message.chat.id, msg)
    elif message.text == "Technical Signals":
        signals = fetch_all_signals()
        msg = "📊 Technical Signals\n\n"
        for coin, tf_data in signals.items():
            msg += f"🔹 {coin}\n"
            for tf, signal in tf_data.items():
                msg += f"   ⏱ {tf}: {signal}\n"
        bot.send_message(message.chat.id, msg)
    elif message.text == "Top Movers":
        movers = fetch_movers()
        msg = "📈 Top Movers:\n"
        for coin, change in movers:
            msg += f"{coin}: {change}%\n"
        bot.send_message(message.chat.id, msg)
    elif message.text == "Add Coin":
        bot.send_message(message.chat.id, "Send coin symbol to add (e.g., BTCUSDT)")
        bot.register_next_step_handler(message, add_coin)
    elif message.text == "Remove Coin":
        bot.send_message(message.chat.id, "Send coin symbol to remove")
        bot.register_next_step_handler(message, remove_coin)

def add_coin(message):
    symbol = message.text.strip().upper()
    if symbol not in coins:
        coins.append(symbol)
        bot.send_message(message.chat.id, f"{symbol} added!")
    else:
        bot.send_message(message.chat.id, f"{symbol} already in your list.")

def remove_coin(message):
    symbol = message.text.strip().upper()
    if symbol in coins:
        coins.remove(symbol)
        bot.send_message(message.chat.id, f"{symbol} removed!")
    else:
        bot.send_message(message.chat.id, f"{symbol} not in your list.")

# === Flask Webhook ===
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# Set webhook
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# Start auto updates in background
threading.Thread(target=send_auto_updates, daemon=True).start()

# Run Flask app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)




