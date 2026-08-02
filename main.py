import threading
import asyncio
import json
import sys
import os
import time
from datetime import datetime
import pandas as pd
import requests
import websockets
from flask import Flask

# Forzar flush inmediato en prints de Render
sys.stdout.reconfigure(line_buffering=True)

# ------------------------------------------
# CONFIGURACIÓN DE DISCORD WEBHOOK
# ------------------------------------------
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1533349076593283252/QPKKfcqt0F1I0WcUEnwl5GjVsQTQYL23BvX8FOYM1p4laseCH0iDNPhdfd0VApHafggJ"

# ------------------------------------------
# SERVIDOR FLASK (Health Check para Render)
# ------------------------------------------
app = Flask(__name__)

@app.route('/')
def health_check():
    return "OK - Bot activo y ejecutándose", 200

# ------------------------------------------
# ALERTAS DISCORD
# ------------------------------------------
def send_discord_alert(action, price, reason, timestamp):
    if not DISCORD_WEBHOOK_URL:
        return
    
    color = 0x3498DB
    if "COMPRAR UP" in action:
        color = 0x2ECC71
    elif "COMPRAR DOWN" in action:
        color = 0xE74C3C
    elif "PROFIT" in action or "CERRAR" in action:
        color = 0xF1C40F

    embed = {
        "title": "🚨 ALERTA KALSHI BTC (FILTRO DE CUOTA ACTIVO)",
        "color": color,
        "fields": [
            {"name": "Acción", "value": f"**{action}**", "inline": False},
            {"name": "Precio BTC Kalshi", "value": f"${price:,.2f}", "inline": True},
            {"name": "Hora", "value": timestamp, "inline": True},
            {"name": "Detalle / Motivo", "value": reason, "inline": False}
        ],
        "footer": {"text": "Bot Estratégico 15m / Excluye Cuotas Bajas (<1.4)"}
    }

    payload = {
        "username": "Bot Kalshi Signals",
        "embeds": [embed]
    }

    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        print(f"[ERROR DISCORD]: {e}", flush=True)

# ------------------------------------------
# ESTRATEGIA Y COINBASE WEBSOCKET
# ------------------------------------------
COINBASE_WS = "wss://ws-feed.exchange.coinbase.com"
candles_1m = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
current_minute_ticks = []
last_sent_action = ""

def load_initial_candles():
    global candles_1m
    try:
        url = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=60"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            df = pd.DataFrame(data, columns=['time', 'low', 'high', 'open', 'close', 'volume'])
            df = df.iloc[::-1].reset_index(drop=True)
            df['timestamp'] = pd.to_datetime(df['time'], unit='s').dt.strftime('%H:%M:00')
            candles_1m = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].tail(30)
            print("✅ Historial inicial de 30 velas cargado exitosamente.", flush=True)
    except Exception as e:
        print(f"[WARN] No se pudo cargar historial previo: {e}", flush=True)

def resample_candles(df, timeframe='15min'):
    if df.empty or len(df) < 5:
        return pd.DataFrame()
    
    df_copy = df.copy()
    df_copy['datetime'] = pd.to_datetime(df_copy['timestamp'], format='%H:%M:%S')
    df_copy.set_index('datetime', inplace=True)
    
    resampled = df_copy.resample(timeframe).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    
    return resampled

def calculate_interval_signals(df_1m):
    if len(df_1m) < 5:
        return "NEUTRAL ⚖️", "RECOLECTANDO VELAS INICIALES"

    now = datetime.now()
    minute_of_hour = now.minute
    interval_start_min = (minute_of_hour // 15) * 15
    minute_in_interval = minute_of_hour - interval_start_min

    df_15m = resample_candles(df_1m, '15min')

    df_1m['ema9'] = df_1m['close'].ewm(span=9, adjust=False).mean()
    df_1m['ema21'] = df_1m['close'].ewm(span=21, adjust=False).mean()
    
    last_1m = df_1m.iloc[-1]
    
    trend_15m = "NEUTRAL"
    if not df_15m.empty and len(df_15m) >= 2:
        df_15m['ema9'] = df_15m['close'].ewm(span=9, adjust=False).mean()
        df_15m['ema21'] = df_15m['close'].ewm(span=21, adjust=False).mean()
        last_15m = df_15m.iloc[-1]
        if last_15m['ema9'] > last_15m['ema21']:
            trend_15m = "ALCISTA"
        elif last_15m['ema9'] < last_15m['ema21']:
            trend_15m = "BAJISTA"

    body = abs(last_1m['close'] - last_1m['open'])
    upper_wick = last_1m['high'] - max(last_1m['close'], last_1m['open'])
    lower_wick = min(last_1m['close'], last_1m['open']) - last_1m['low']

    if upper_wick > (body * 1.3) and upper_wick > 0:
        return "💰 CERRAR / TOMAR PROFIT (UP)", f"AGOTAMIENTO EN MINUTO {minute_in_interval}/15"
    
    if lower_wick > (body * 1.3) and lower_wick > 0:
        return "💰 CERRAR / TOMAR PROFIT (DOWN)", f"AGOTAMIENTO EN MINUTO {minute_in_interval}/15"

    dist_5m = abs(last_1m['close'] - df_1m['open'].tail(5).iloc[0])
    if minute_in_interval >= 10 and dist_5m > 120:
        return "NEUTRAL ⚖️", f"CUOTA MUY BAJA EN KALSHI (~1.2) - MOVIMIENTO CASI EXTENDIDO"

    ema_bull = last_1m['ema9'] > last_1m['ema21']
    ema_bear = last_1m['ema9'] < last_1m['ema21']
    green = last_1m['close'] > last_1m['open']
    red = last_1m['close'] < last_1m['open']

    if minute_in_interval <= 3:
        if ema_bull and green:
            return "🔥 INICIO BLOQUE: COMPRAR UP 🚀", f"BUENA CUOTA (INTERVALO {interval_start_min}m)"
        elif ema_bear and red:
            return "🔥 INICIO BLOQUE: COMPRAR DOWN 📉", f"BUENA CUOTA (INTERVALO {interval_start_min}m)"

    elif 4 <= minute_in_interval <= 9:
        if ema_bull and green and trend_15m == "ALCISTA":
            return "⚡ RE-ENTRADA: COMPRAR UP 🚀", f"CUOTA ACEPTABLE ({minute_in_interval}m)"
        elif ema_bear and red and trend_15m == "BAJISTA":
            return "⚡ RE-ENTRADA: COMPRAR DOWN 📉", f"CUOTA ACEPTABLE ({minute_in_interval}m)"

    return "NEUTRAL ⚖️", f"SIN PATRÓN O CUOTA NO ATRACTIVA ({minute_in_interval}/15m)"

async def coinbase_websocket_listener():
    global candles_1m, current_minute_ticks, last_sent_action
    
    subscribe_msg = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["ticker"]
    }

    while True:
        try:
            async with websockets.connect(COINBASE_WS) as ws:
                await ws.send(json.dumps(subscribe_msg))
                print("🟢 Conectado a Coinbase Feed...", flush=True)
                
                last_minute = datetime.now().minute
                
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    if data.get('type') == 'ticker' and 'price' in data:
                        price = float(data['price'])
                        size = float(data.get('last_size', 0))
                        now = datetime.now()
                        
                        current_minute_ticks.append({'price': price, 'size': size})
                        
                        if now.minute != last_minute:
                            if current_minute_ticks:
                                prices = [t['price'] for t in current_minute_ticks]
                                open_p = prices[0]
                                high_p = max(prices)
                                low_p = min(prices)
                                close_p = prices[-1]
                                vol = sum([t['size'] for t in current_minute_ticks])
                                t_stamp = now.strftime('%H:%M:00')

                                new_row = pd.DataFrame([{
                                    'timestamp': t_stamp, 'open': open_p, 
                                    'high': high_p, 'low': low_p, 
                                    'close': close_p, 'volume': vol
                                }])
                                
                                candles_1m = pd.concat([candles_1m, new_row], ignore_index=True)
                                action, reason = calculate_interval_signals(candles_1m)
                                
                                print(f"[{t_stamp}] BTC Kalshi: ${close_p:,.2f} | ACCIÓN: {action} ({reason})", flush=True)

                                if "COMPRAR" in action or "CERRAR" in action or "PROFIT" in action:
                                    if action != last_sent_action:
                                        send_discord_alert(action, close_p, reason, t_stamp)
                                        last_sent_action = action

                                current_minute_ticks = []
                            
                            last_minute = now.minute

        except Exception as e:
            print(f"[RECONECTANDO COINBASE]: {e}", flush=True)
            await asyncio.sleep(5)

def run_bot():
    load_initial_candles()
    asyncio.run(coinbase_websocket_listener())

# Iniciar el Bot en Hilo Secundario
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
