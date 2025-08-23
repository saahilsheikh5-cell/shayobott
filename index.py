
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
coin_signals = {}
last_alerted = {}

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

def generate_signal(symbol, interval):
    df = fetch_candles(symbol, interval)
    ind = calculate_indicators(df)
    if not ind:
        return f"⏱ {interval} — ⚪ HOLD — {symbol} | No data", ''
    signal = "HOLD"
    strong_flag = ''
    icon = '⚪'
    color_icon = ''
    if ind['MACD'] > ind['Signal'] and ind['RSI'] < 70:
        signal = "BUY"
        icon = '🔺'
        color_icon = '🟢'
        if ind['RSI'] < 60:
            signal = "STRONG BUY"
            strong_flag = 'BUY'
    elif ind['MACD'] < ind['Signal'] and ind['RSI'] > 30:
        signal = "SELL"
        icon = '🔻'
        color_icon = '🔴'
        if ind['RSI'] > 40:
            signal = "STRONG SELL"
            strong_flag = 'SELL'
    price = ind['Close']
    sl = round(price*0.98, 2) if 'BUY' in signal else round(price*1.02,2)
    t1 = round(price*1.02, 2) if 'BUY' in signal else round(price*0.98,2)
    t2 = round(price*1.04, 2) if 'BUY' in signal else round(price*0.96,2)
    return (f"⏱ {interval} — {icon}{color_icon} {signal} — {symbol}\n"
            f"Price: {price} | SL: {sl}, T1: {t1}, T2: {t2}\n"
            f"RSI: {ind['RSI']:.2f}, MACD: {ind['MACD']:.2f}, Signal: {ind['Signal']:.2f}"), strong_flag

INTERVALS = {'1m':60, '5m':300, '15m':900, '1h':3600, '4h':14400, '1d':86400}

# === Update Signals for Auto Alerts ===
def update_coin_signals(symbol, timeframe):
    if symbol not in last_alerted:
        last_alerted[symbol] = {tf: '' for tf in INTERVALS.keys()}
    while True:
        signal_text, strong_flag = generate_signal(symbol, timeframe)
        coin_signals[symbol] = {timeframe: signal_text}
        if strong_flag and chat_id:
            if strong_flag != last_alerted[symbol].get(timeframe, ''):
                bot.send_message(chat_id, f"🚨 Strong Signal Detected!\n{signal_text}")
                last_alerted[symbol][timeframe] = strong_flag
        time.sleep(60)

# === Fetch Top Movers ===
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
    markup.row("Auto Signals")  # New button for auto alerts
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
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("1m", "5m", "15m")
        markup.row("1h", "1d")
        bot.send_message(chat_id, "Select timeframe to view Technical Signals:", reply_markup=markup)

    elif message.text == "Auto Signals":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("1m", "5m", "15m")
        markup.row("1h", "1d")
        bot.send_message(chat_id, "Select timeframe for Auto Signals:", reply_markup=markup)

    elif message.text in INTERVALS.keys():
        # Determine if user came from Technical Signals or Auto Signals by context
        # Here we assume auto alerts if a coin has active thread, else manual display
        if message.text:  # Manual Technical Signals
            msg = f"📊 Technical Signals — {message.text}\n\n"
            for coin in coins:
                signal_text, _ = generate_signal(coin, message.text)
                msg += f"{signal_text}\n"
            bot.send_message(chat_id, msg)
        else:  # Auto Signals
            for coin in coins:
                threading.Thread(target=update_coin_signals, args=(coin, message.text), daemon=True).start()
            bot.send_message(chat_id, f"Auto alerts started for {message.text} timeframe.")

    elif message.text == "Top Movers":
        movers = fetch_top_movers()
        msg = "📈 Top Movers\n\n"
        for interval, coins_list in movers.items():
            msg += f"⏱ {interval}:\n"
            for sym, change in coins_list:
                change_icon = '🟢' if change > 0 else '🔴'
                msg += f"   {sym}: {change_icon} {change:.2f}%\n"
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
    else:
        bot.send_message(chat_id, f"{symbol} already in your list.")

def remove_coin(message):
    symbol = message.text.strip().upper()
    if symbol in coins:
        coins.remove(symbol)
        coin_signals.pop(symbol, None)
        last_alerted.pop(symbol, None)
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)







