import os
import telebot
import requests
import threading
import time
import datetime
from telebot import types

# === CONFIG ===
BOT_TOKEN = "7638935379:AAEmLD7JHLZ36Ywh5tvmlP1F8xzrcNrym_Q"
WEBHOOK_URL = "https://shayobott.onrender.com/" + BOT_TOKEN
CHAT_ID = 1263295916   # Your Telegram ID

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Default portfolio
portfolio = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "AAVEUSDT"]

# Auto update state
auto_update_interval = None
auto_update_thread = None
stop_auto_update = False

# === BINANCE API HELPERS ===
def get_price(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        res = requests.get(url, timeout=10)
        return float(res.json()["price"])
    except:
        return None

def get_movers(interval="1h"):
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        res = requests.get(url, timeout=10).json()
        movers = []

        for coin in res:
            change = None
            if interval == "5m":
                kline_url = f"https://api.binance.com/api/v3/klines?symbol={coin['symbol']}&interval=5m&limit=2"
                kline_res = requests.get(kline_url, timeout=10).json()
                if isinstance(kline_res, list) and len(kline_res) >= 2:
                    old_price = float(kline_res[0][4])
                    new_price = float(kline_res[1][4])
                    change = ((new_price - old_price) / old_price) * 100
            elif interval in ["1h", "24h"]:
                change = float(coin.get("priceChangePercent", 0))

            if change is not None:
                movers.append((coin["symbol"], change))

        movers.sort(key=lambda x: abs(x[1]), reverse=True)
        return movers[:10]
    except:
        return []

# === SIGNAL GENERATOR ===
def generate_signal(symbol, interval="1h"):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=50"
        data = requests.get(url, timeout=10).json()
        closes = [float(x[4]) for x in data]

        if len(closes) < 14:
            return "No clear signal"

        sma5 = sum(closes[-5:]) / 5
        sma14 = sum(closes[-14:]) / 14

        if sma5 > sma14 * 1.01:
            return "📈 Strong Buy"
        elif sma5 < sma14 * 0.99:
            return "📉 Strong Sell"
        else:
            return "➖ No clear signal"
    except:
        return "Error"

# === BOT COMMANDS ===
@bot.message_handler(commands=["start"])
def start(message):
    show_main_menu(message.chat.id)

def show_main_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 Portfolio", "📈 Live Prices")
    markup.add("📑 Technical Signals", "🚀 Movers")
    markup.add("➕ Add Coin", "➖ Remove Coin")
    markup.add("⚙️ Settings", "⛔ Stop Auto Updates")
    bot.send_message(chat_id, "Welcome! Choose an option:", reply_markup=markup)

# === BUTTON ACTIONS ===
@bot.message_handler(func=lambda m: m.text == "📊 Portfolio")
def portfolio_handler(message):
    msg = "📊 Your Portfolio:\n\n"
    total = 0
    for coin in portfolio:
        price = get_price(coin)
        if price:
            msg += f"{coin}: ${price:.2f}\n"
            total += price
        else:
            msg += f"{coin}: Error fetching price\n"
    msg += f"\n💰 Total Portfolio Value: ${total:.2f}"
    bot.send_message(message.chat.id, msg)

@bot.message_handler(func=lambda m: m.text == "📈 Live Prices")
def live_prices(message):
    msg = "📈 Live Prices:\n\n"
    for coin in portfolio:
        price = get_price(coin)
        msg += f"{coin}: ${price:.2f}\n" if price else f"{coin}: Error fetching price\n"
    bot.send_message(message.chat.id, msg)

@bot.message_handler(func=lambda m: m.text == "📑 Technical Signals")
def signals_handler(message):
    msg = "📊 Technical Signals\n\n"
    for coin in portfolio:
        msg += f"🔹 {coin}\n"
        for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
            signal = generate_signal(coin, tf)
            msg += f"   ⏱ {tf}: {signal}\n"
        msg += "\n"
    bot.send_message(message.chat.id, msg)

@bot.message_handler(func=lambda m: m.text == "🚀 Movers")
def movers_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🚀 5m Movers", "🚀 1h Movers", "🚀 24h Movers")
    markup.add("⬅️ Back")
    bot.send_message(message.chat.id, "Choose movers interval:", reply_markup=markup)

@bot.message_handler(func=lambda m: "Movers" in m.text)
def movers_handler(message):
    interval = "24h"
    if "5m" in message.text: interval = "5m"
    elif "1h" in message.text: interval = "1h"
    movers = get_movers(interval)
    msg = f"🚀 Top {interval} Movers:\n\n"
    for sym, change in movers:
        msg += f"{sym}: {change:.2f}%\n"
    bot.send_message(message.chat.id, msg)

@bot.message_handler(func=lambda m: m.text == "➕ Add Coin")
def add_coin(message):
    bot.send_message(message.chat.id, "Send me the coin symbol (e.g., MATICUSDT):")
    bot.register_next_step_handler(message, process_add_coin)

def process_add_coin(message):
    coin = message.text.upper()
    if coin not in portfolio:
        portfolio.append(coin)
        bot.send_message(message.chat.id, f"✅ {coin} added to portfolio.")
    else:
        bot.send_message(message.chat.id, f"{coin} already exists.")

@bot.message_handler(func=lambda m: m.text == "➖ Remove Coin")
def remove_coin(message):
    bot.send_message(message.chat.id, "Send me the coin symbol to remove:")
    bot.register_next_step_handler(message, process_remove_coin)

def process_remove_coin(message):
    coin = message.text.upper()
    if coin in portfolio:
        portfolio.remove(coin)
        bot.send_message(message.chat.id, f"❌ {coin} removed from portfolio.")
    else:
        bot.send_message(message.chat.id, f"{coin} not found.")

# === SETTINGS ===
@bot.message_handler(func=lambda m: m.text == "⚙️ Settings")
def settings_handler(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("⏱ Auto 1m", "⏱ Auto 5m")
    markup.add("⏱ Auto 15m", "⏱ Auto 1h")
    markup.add("⬅️ Back")
    bot.send_message(message.chat.id, "Select auto-update interval:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text.startswith("⏱ Auto"))
def set_auto_update(message):
    global auto_update_interval, stop_auto_update, auto_update_thread
    stop_auto_update = False
    if "1m" in message.text: auto_update_interval = 60
    elif "5m" in message.text: auto_update_interval = 300
    elif "15m" in message.text: auto_update_interval = 900
    elif "1h" in message.text: auto_update_interval = 3600

    if auto_update_thread is None or not auto_update_thread.is_alive():
        auto_update_thread = threading.Thread(target=auto_update_loop, daemon=True)
        auto_update_thread.start()

    bot.send_message(message.chat.id, f"✅ Auto-updates every {message.text.split()[1]} started.")

def auto_update_loop():
    global stop_auto_update
    while not stop_auto_update:
        try:
            msg = "📊 Auto Update (Signals)\n\n"
            for coin in portfolio:
                signal = generate_signal(coin, "5m")
                msg += f"{coin}: {signal}\n"
            bot.send_message(CHAT_ID, msg)
        except Exception as e:
            print("Auto-update error:", e)
        time.sleep(auto_update_interval)

@bot.message_handler(func=lambda m: m.text == "⛔ Stop Auto Updates")
def stop_updates(message):
    global stop_auto_update
    stop_auto_update = True
    bot.send_message(message.chat.id, "⛔ Auto-updates stopped.")

@bot.message_handler(func=lambda m: m.text == "⬅️ Back")
def back_to_menu(message):
    show_main_menu(message.chat.id)

# === DAILY SUMMARY AT MIDNIGHT ===
def daily_summary():
    while True:
        now = datetime.datetime.now()
        if now.hour == 0 and now.minute == 0:  # midnight
            try:
                msg = "🌙 Daily Summary\n\n"
                total = 0
                for coin in portfolio:
                    price = get_price(coin)
                    signal = generate_signal(coin, "1h")
                    if price:
                        msg += f"{coin}: ${price:.2f} | {signal}\n"
                        total += price
                msg += f"\n💰 Total Portfolio Value: ${total:.2f}"
                bot.send_message(CHAT_ID, msg)
            except Exception as e:
                print("Daily summary error:", e)
            time.sleep(60)  # prevent multiple sends in the same minute
        time.sleep(30)

threading.Thread(target=daily_summary, daemon=True).start()

# === START POLLING ===
print("Bot running...")
bot.infinity_polling()
