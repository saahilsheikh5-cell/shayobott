import os
import requests
import threading
import time
from flask import Flask, request
import telebot
from telebot import types

# === CONFIG ===
BOT_TOKEN = "7638935379:AAEmLD7JHLZ36Ywh5tvmlP1F8xzrcNrym_Q"
WEBHOOK_URL = "https://shayobott-2.onrender.com/" + BOT_TOKEN

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Portfolio coins (modifiable with add/remove buttons)
coins = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "AAVEUSDT"]
update_interval = 300  # default 5 minutes

# === Helper Functions ===

def fetch_price(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        res = requests.get(url, timeout=5).json()
        return float(res["price"])
    except:
        return None

def fetch_top_movers(interval="1h"):
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        data = requests.get(url, timeout=5).json()
        movers = sorted(data, key=lambda x: abs(float(x["priceChangePercent"])), reverse=True)
        top = movers[:5]
        return [f"{m['symbol']}: {float(m['priceChangePercent']):.2f}%" for m in top]
    except:
        return ["Error fetching movers"]

def analyze_macd(symbol):
    # Placeholder logic, integrate real MACD computation
    return "BUY"

def analyze_rsi(symbol):
    # Placeholder logic
    return "BUY"

def analyze_ma(symbol):
    # Placeholder logic
    return "BUY"

def generate_signal(symbol):
    price = fetch_price(symbol)
    if price is None:
        return f"{symbol}: Error fetching price"

    signals = [analyze_macd(symbol), analyze_rsi(symbol), analyze_ma(symbol)]

    if signals.count("BUY") == 3:
        prefix = "✅ STRONG BUY"
    elif signals.count("BUY") >= 2:
        prefix = "✅ BUY"
    elif signals.count("SELL") == 3:
        prefix = "❌ STRONG SELL"
    elif signals.count("SELL") >= 2:
        prefix = "❌ SELL"
    else:
        prefix = "⚪ No clear signal"

    # Correct SL/TP
    sl = price * 0.98 if "BUY" in prefix else price * 1.02
    t1 = price * 1.02 if "BUY" in prefix else price * 0.98
    t2 = price * 1.05 if "BUY" in prefix else price * 0.95

    return f"{prefix} — {symbol} | Price: {price:.4f} | SL: {sl:.4f}, T1: {t1:.4f}, T2: {t2:.4f}"

# === Bot Commands ===

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton("📈 Live Prices")
    btn2 = types.KeyboardButton("📊 Portfolio")
    btn3 = types.KeyboardButton("🛠 Technical Signals")
    btn4 = types.KeyboardButton("➕ Add Coin")
    btn5 = types.KeyboardButton("➖ Remove Coin")
    markup.add(btn1, btn2, btn3, btn4, btn5)
    bot.send_message(message.chat.id, "Welcome! Choose an option:", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle_buttons(message):
    chat_id = message.chat.id
    text = message.text

    if text == "📈 Live Prices":
        msg = ""
        for c in coins:
            p = fetch_price(c)
            msg += f"{c}: {p if p else 'Error fetching price'}\n"
        bot.send_message(chat_id, msg)

    elif text == "📊 Portfolio":
        total = 0
        msg = "📊 Your Portfolio:\n\n"
        for c in coins:
            price = fetch_price(c)
            total += price if price else 0
            msg += f"{c}: {price if price else 'Error fetching price'}\n"
        msg += f"\n💰 Total Portfolio Value: ${total:.2f}"
        bot.send_message(chat_id, msg)

    elif text == "🛠 Technical Signals":
        msg = "📊 Technical Signals\n\n"
        for c in coins:
            msg += generate_signal(c) + "\n\n"
        bot.send_message(chat_id, msg)

    elif text == "➕ Add Coin":
        bot.send_message(chat_id, "Send me coin symbol to add (e.g., BTCUSDT)")

    elif text == "➖ Remove Coin":
        bot.send_message(chat_id, "Send me coin symbol to remove (e.g., BTCUSDT)")

# === Webhook Setup ===
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def index():
    return "Bot is running!", 200

# === Auto Updates ===
def auto_update():
    while True:
        time.sleep(update_interval)
        # Auto send signals
        for c in coins:
            chat_id = 1263295916  # your chat id
            bot.send_message(chat_id, generate_signal(c))

threading.Thread(target=auto_update, daemon=True).start()

# === Start webhook server ===
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=port)



