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

coins = []
chat_id = None

# Store latest signals for fast access
coin_signals = {}

# === Binance API ===
BASE_URL = 'https://api.binance.com/api/v3'

def fetch_price(symbol):
    try:
        res = requests.get(f'{BASE_URL}/ticker/price', params={'symbol': symbol})
        return float(res.json()['price'])
    except:
        return None

def fetch_candles(symbol, interval='5m', limit=100):
    try:
        res = requests.get(f'{BASE_URL}/klines', params={'symbol': symbol, 'interval': interval, 'limit': limit})
        df = pd.DataFrame(res.json(), columns=["Open time","Open","High","Low","Close","Volume","Close time","Quote asset volume","Number of trades","Taker buy base asset volume","Taker buy quote asset volume","Ignore"])
        df = df[['Open','High','Low','Close','Volume']].astype(float)
        return df
    except:
        return pd.DataFrame()

# === Indicators ===

def calculate_indicators(df):
    indicators = {}
    if df.empty:
        return indicators
    df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    indicators['MACD'] = df['MACD'].iloc[-1]
    indicators['Signal'] = df['Signal'].iloc[-1]
    indicators['RSI'] = df['RSI'].iloc[-1]
    indicators['Close'] = df['Close'].iloc[-1]
    return indicators

# === Signal Generation ===

def generate_signal(symbol, interval):
    df = fetch_candles(symbol, interval)
    ind = calculate_indicators(df)
    if not ind:
        return "No data"
    signal = "HOLD"
    strong = ""
    if ind['MACD'] > ind['Signal'] and ind['RSI'] < 70:
        signal = "BUY"
        if ind['RSI'] < 60:
            strong = "STRONG "
    elif ind['MACD'] < ind['Signal'] and ind['RSI'] > 30:
        signal = "SELL"
        if ind['RSI'] > 40:
            strong = "STRONG "
    price = ind['Close']
    sl = round(price*0.98, 2) if signal == 'BUY' else round(price*1.02,2)
    t1 = round(price*1.02, 2) if signal == 'BUY' else round(price*0.98,2)
    t2 = round(price*1.04, 2) if signal == 'BUY' else round(price*0.96,2)
    return f"{strong}{signal} — {symbol} | Price: {price} | SL: {sl}, T1: {t1}, T2: {t2}"

# === Real-time update per coin ===
INTERVALS = {'1m':60, '5m':300, '15m':900, '1h':3600, '4h':14400, '1d':86400}

def update_coin_signals(symbol):
    while True:
        coin_signals[symbol] = {}
        for tf in INTERVALS.keys():
            coin_signals[symbol][tf] = generate_signal(symbol, tf)
        time.sleep(60)  # Update every minute for fast refresh

# === Top Movers ===
def fetch_top_movers():
    movers = {}
    try:
        res = requests.get(f'{BASE_URL}/ticker/24hr').json()
        df = pd.DataFrame(res)
        df['priceChangePercent'] = df['priceChangePercent'].astype(float)
        for interval in ['5m','1h','24h']:
            top = df.sort_values('priceChangePercent', ascending=False).head(10)
            movers[interval] = [(row['symbol'], row['priceChangePercent']) for idx,row in top.iterrows()]
    except:
        movers = {'5m': [], '1h': [], '24h': []}
    return movers

# === Telegram Handlers ===
@bot.message_handler(commands=['start'])
def start_handler(message):
    global chat_id
    chat_id = message.chat.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Live Prices", "Technical Signals")
    markup.row("Top Movers", "Add Coin", "Remove Coin")
    bot.send_message(chat_id, "Welcome! Use the buttons below to control the bot.", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    global chat_id
    chat_id = message.chat.id
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
        bot.send_message(chat_id, msg)

    elif message.text == "Technical Signals":
        msg = "📊 Technical Signals\n\n"
        for coin in coins:
            msg += f"🔹 {coin}\n"
            for tf, signal in coin_signals.get(coin, {}).items():
                msg += f"   ⏱ {tf}: {signal}\n"
        bot.send_message(chat_id, msg)

    elif message.text == "Top Movers":
        movers = fetch_top_movers()
        msg = "📈 Top Movers\n\n"
        for interval, coins_list in movers.items():
            msg += f"⏱ {interval}:\n"
            for sym, change in coins_list:
                msg += f"   {sym}: {change:.2f}%\n"
        bot.send_message(chat_id, msg)

    elif message.text == "Add Coin":
        bot.send_message(chat_id, "Send coin symbol to add (e.g., BTCUSDT)")
        bot.register_next_step_handler(message, add_coin)

    elif message.text == "Remove Coin":
        bot.send_message(chat_id, "Send coin symbol to remove")
        bot.register_next_step_handler(message, remove_coin)

def add_coin(message):
    symbol = message.text.strip().upper()
    if symbol not in coins:
        coins.append(symbol)
        bot.send_message(chat_id, f"{symbol} added!")
        # Start real-time thread
        threading.Thread(target=update_coin_signals, args=(symbol,), daemon=True).start()
    else:
        bot.send_message(chat_id, f"{symbol} already in your list.")

def remove_coin(message):
    symbol = message.text.strip().upper()
    if symbol in coins:
        coins.remove(symbol)
        coin_signals.pop(symbol, None)
        bot.send_message(chat_id, f"{symbol} removed!")
    else:
        bot.send_message(chat_id, f"{symbol} not in your list.")

# === Flask Webhook ===
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# Run Flask app
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)





