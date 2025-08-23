import os
import telebot
import requests
import threading
import time
from telebot import types

# ================= CONFIG =================
BOT_TOKEN = "7638935379:AAEmLD7JHLZ36Ywh5tvmlP1F8xzrcNrym_Q"
WEBHOOK_URL = "https://shayobott.onrender.com/" + BOT_TOKEN
CHAT_ID = 1263295916  # your Telegram ID

bot = telebot.TeleBot(BOT_TOKEN)

# Coin list
coins = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "AAVEUSDT"]

# Default auto-update interval in seconds
update_interval = 300  # 5 minutes

# ==========================================

def fetch_price(symbol):
    try:
        data = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}").json()
        return float(data["price"])
    except:
        return None

def fetch_movers(interval="1h"):
    try:
        data = requests.get(f"https://api.binance.com/api/v3/ticker/24hr").json()
        movers = sorted(data, key=lambda x: float(x["priceChangePercent"]), reverse=True)
        top = []
        for coin in movers:
            if coin["symbol"] in coins:
                top.append(f"{coin['symbol']}: {coin['priceChangePercent']}%")
                if len(top) >= 5:
                    break
        return top
    except:
        return ["Error fetching movers"]

def generate_signal(symbol, interval, signal_type, entry_price, atr=0, confirmations=1, max_confirmations=3):
    if signal_type == "BUY":
        sl = round(entry_price - atr, 2)
        t1 = round(entry_price + atr * 1, 2)
        t2 = round(entry_price + atr * 2, 2)
    elif signal_type == "SELL":
        sl = round(entry_price + atr, 2)
        t1 = round(entry_price - atr * 1, 2)
        t2 = round(entry_price - atr * 2, 2)
    else:
        return None
    strength = "STRONG " if confirmations == max_confirmations else ""
    return f"{strength}{signal_type} — {symbol} {interval} | Price: {entry_price} | SL: {sl}, T1: {t1}, T2: {t2}"

def send_portfolio():
    msg = "📊 Your Portfolio:\n\n"
    total = 0
    for coin in coins:
        price = fetch_price(coin)
        if price is None:
            msg += f"{coin}: Error fetching price\n"
        else:
            msg += f"{coin}: ${price}\n"
            total += price
    msg += f"\n💰 Total Portfolio Value: ${total:.2f}"
    bot.send_message(CHAT_ID, msg)

def send_signals():
    msg = "📊 Technical Signals\n\n"
    for coin in coins:
        price = fetch_price(coin)
        if price is None:
            msg += f"{coin}: No price data\n"
            continue
        # Example: you can replace ATR and confirmations with your own logic
        atr = price * 0.01
        buy_signal = generate_signal(coin, "1h", "BUY", price, atr, confirmations=3)
        sell_signal = generate_signal(coin, "1h", "SELL", price, atr, confirmations=3)
        msg += f"{buy_signal}\n{sell_signal}\n\n"
    bot.send_message(CHAT_ID, msg)

def send_movers():
    msg = "🚀 Top Movers:\n\n"
    for interval in ["5m", "1h", "24h"]:
        movers = fetch_movers(interval)
        msg += f"⏱ {interval}:\n" + "\n".join(movers) + "\n\n"
    bot.send_message(CHAT_ID, msg)

def auto_update():
    while True:
        send_portfolio()
        send_signals()
        send_movers()
        time.sleep(update_interval)

# ================= TELEGRAM COMMANDS =================
@bot.message_handler(commands=["start"])
def start(message):
    markup = types.ReplyKeyboardMarkup(row_width=2)
    markup.add("Live Prices", "Technical Signals", "Top Movers", "Add Coin", "Remove Coin")
    bot.send_message(message.chat.id, "Welcome! Choose an option:", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    global update_interval
    if message.text == "Live Prices":
        send_portfolio()
    elif message.text == "Technical Signals":
        send_signals()
    elif message.text == "Top Movers":
        send_movers()
    elif message.text == "Add Coin":
        bot.send_message(message.chat.id, "Send coin symbol to add (e.g., BTCUSDT)")
    elif message.text == "Remove Coin":
        bot.send_message(message.chat.id, "Send coin symbol to remove")
    else:
        coin = message.text.upper()
        if coin in coins:
            coins.remove(coin)
            bot.send_message(message.chat.id, f"{coin} removed from your list.")
        else:
            coins.append(coin)
            bot.send_message(message.chat.id, f"{coin} added to your list.")

# ================= START AUTO-UPDATE THREAD =================
threading.Thread(target=auto_update, daemon=True).start()

# ================= SET WEBHOOK =================
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)


