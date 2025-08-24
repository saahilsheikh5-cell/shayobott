import os
import telebot
import requests
import time
import threading
from flask import Flask, request
from telebot import types

# === CONFIG ===
BOT_TOKEN = "7638935379:AAEmLD7JHLZ36Ywh5tvmlP1F8xzrcNrym_Q"
WEBHOOK_URL = "https://shayobott-2.onrender.com/" + BOT_TOKEN
ALL_COINS_URL = "https://api.binance.com/api/v3/ticker/price"

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)
app = Flask(__name__)

# === GLOBALS ===
user_coins = {}  # {chat_id: [symbols]}
auto_signal_threads = {}  # {chat_id: thread}
last_signals = {}  # remembers last signals sent {chat_id: {symbol: signal}}

# === UTILS ===
def get_coin_name(symbol):
    """Format symbol like BTCUSDT -> BTC"""
    if symbol.endswith("USDT"):
        return symbol.replace("USDT", "")
    if symbol.endswith("BUSD"):
        return symbol.replace("BUSD", "")
    if symbol.endswith("USDC"):
        return symbol.replace("USDC", "")
    return symbol

def analyze(symbol, interval="15m"):
    """Dummy analyzer (replace with TA API if available)"""
    try:
        # Binance kline
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=14"
        resp = requests.get(url, timeout=10).json()
        closes = [float(c[4]) for c in resp]
        price = closes[-1]

        # RSI approx
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            if diff > 0:
                gains.append(diff)
            else:
                losses.append(abs(diff))

        avg_gain = sum(gains)/14 if gains else 0.001
        avg_loss = sum(losses)/14 if losses else 0.001
        rs = avg_gain/avg_loss
        rsi = 100 - (100/(1+rs))

        # classify
        if rsi >= 80:
            return {"signal": "Strong Sell", "emoji": "🔻🔴", "price": price}
        elif rsi <= 20:
            return {"signal": "Strong Buy", "emoji": "🔺🟢", "price": price}
        elif rsi >= 60:
            return {"signal": "Sell", "emoji": "🔻🟠", "price": price}
        elif rsi <= 40:
            return {"signal": "Buy", "emoji": "🔺🟡", "price": price}
        else:
            return {"signal": "Neutral", "emoji": "⚪", "price": price}

    except Exception as e:
        print("Analysis error:", e)
        return None

# === MENU ===
@bot.message_handler(commands=["start"])
def start(msg):
    chat_id = msg.chat.id
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Add Coins", "📂 My Coins")
    kb.add("📊 Technical Analysis", "📈 Movers")
    kb.add("🤖 Auto Signals")
    bot.send_message(chat_id, "Welcome to SaahilCryptoBot 🚀", reply_markup=kb)

# === ADD COINS ===
@bot.message_handler(func=lambda m: m.text=="➕ Add Coins")
def add_coins(msg):
    bot.send_message(msg.chat.id, "Send me the coin symbol (e.g., BTCUSDT).")

@bot.message_handler(func=lambda m: m.text=="📂 My Coins")
def my_coins(msg):
    coins = user_coins.get(msg.chat.id, [])
    if not coins:
        bot.send_message(msg.chat.id, "You haven’t added any coins yet.")
    else:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for c in coins:
            kb.add(c)
        kb.add("⬅️ Back")
        bot.send_message(msg.chat.id, "Your Coins:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text not in ["📂 My Coins","➕ Add Coins","📊 Technical Analysis","📈 Movers","🤖 Auto Signals","⬅️ Back"])
def save_coin(msg):
    sym = msg.text.upper()
    user_coins.setdefault(msg.chat.id, [])
    if sym not in user_coins[msg.chat.id]:
        user_coins[msg.chat.id].append(sym)
        bot.send_message(msg.chat.id, f"✅ {sym} added to your list!")

# === TECHNICAL ANALYSIS ===
@bot.message_handler(func=lambda m: m.text=="📊 Technical Analysis")
def tech_analysis(msg):
    coins = user_coins.get(msg.chat.id, [])
    if not coins:
        bot.send_message(msg.chat.id, "No coins added. Add first with ➕ Add Coins.")
        return

    for coin in coins:
        text = f"🔎 Technical Analysis for {coin}:\n"
        for tf in ["1m","5m","15m","1h","1d"]:
            res = analyze(coin, tf)
            if res:
                text += f"\n⏰ {tf}: {res['emoji']} {res['signal']} (Price ${res['price']})"
            else:
                text += f"\n⏰ {tf}: Error fetching"
        bot.send_message(msg.chat.id, text)

# === AUTO SIGNALS ===
def run_auto_signals(chat_id):
    global last_signals
    last_signals.setdefault(chat_id, {})
    sleep_time = 900  # 15m

    while True:
        try:
            data = requests.get(ALL_COINS_URL, timeout=10).json()
            for coin_data in data:
                sym = coin_data["symbol"]

                res = analyze(sym, "15m")
                if res and ("Strong" in res["signal"]):
                    prev = last_signals[chat_id].get(sym)
                    if prev != res["signal"]:
                        bot.send_message(
                            chat_id,
                            f"🪙 {get_coin_name(sym)} | ${res['price']}\n"
                            f"{res['emoji']} {res['signal']}"
                        )
                        last_signals[chat_id][sym] = res["signal"]
        except Exception as e:
            print("Auto signal error:", e)

        time.sleep(sleep_time)

@bot.message_handler(func=lambda m: m.text=="🤖 Auto Signals")
def auto_signals(msg):
    if msg.chat.id in auto_signal_threads and auto_signal_threads[msg.chat.id].is_alive():
        bot.send_message(msg.chat.id, "⚡ Auto signals already running (15m).")
    else:
        t = threading.Thread(target=run_auto_signals, args=(msg.chat.id,), daemon=True)
        auto_signal_threads[msg.chat.id] = t
        t.start()
        bot.send_message(msg.chat.id, "✅ Auto signals started (15m).")

# === MOVERS (top movers placeholder) ===
@bot.message_handler(func=lambda m: m.text=="📈 Movers")
def movers(msg):
    bot.send_message(msg.chat.id, "🚀 Movers feature coming soon.")

# === FLASK WEBHOOK ===
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = request.stream.read().decode("utf-8")
    bot.process_new_updates([telebot.types.Update.de_json(update)])
    return "!", 200

@app.route("/")
def index():
    return "Bot running!", 200

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

