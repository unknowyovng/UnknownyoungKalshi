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
# SERVIDOR FLASK (Health Check)
# ------------------------------------------
app = Flask(__name__)

@app.route('/')
def health_check():
    return "OK - Bot Kalshi Activo", 200

# ------------------------------------------
# ENVÍO DE ALERTAS
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
        "title": "🚨 SEÑAL KALSHI BTC 15M",
        "color": color,
        "fields": [
            {"name": "Acción", "value": f"**{action}**", "inline": False},
            {"name": "Precio BTC", "value": f"${price:,.2f}", "inline": True},
            {"name": "Hora", "value": timestamp, "inline": True},
            {"name": "Detalle", "value": reason, "inline": False}
        ],
        "footer": {"text": "Bot Estratégico Kalshi"}
    }

    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"username": "Bot Kalshi Signals", "embeds": [embed]}, timeout=5)
    except Exception as e:
        print(f"[ERROR DISCORD]: {e}", flush=True)

# ------------------------------------------
# LOGICA PRINCIPAL DE ESTRATEGIA
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
        print(f"[WARN] Error cargando velas iniciales: {e}", flush=True)

def evaluate_signals(df_1m):
    if len(df_1m) < 5:
        return "NEUTRAL ⚖️", "Cargando datos..."

    now = datetime.now()
    min_in_15 = now.minute % 15

    # Indicadores Rápidos
    df_1m['ema9'] = df_1m['close'].ewm(span=9, adjust=False).mean()
    df_1m['ema21'] = df_1m['close'].ewm(span=21, adjust=False).mean()

    last = df_1m.iloc[-1]
    prev = df_1m.iloc[-2]

    # Cierre por mecha/rechazo en cualquier minuto
    body = abs(last['close'] - last['open'])
    upper_wick = last['high'] - max(last['close'], last['open'])
    lower_wick = min(last['close'], last['open']) - last['low']

    if upper_wick > (body * 1.5) and upper_wick > 0:
        return "💰 CERRAR / PROFIT (UP)", f"Rechazo en min {min_in_15}/15"
    if lower_wick > (body * 1.5) and lower_wick > 0:
        return "💰 CERRAR / PROFIT (DOWN)", f"Rechazo en min {min_in_15}/15"

    # Bloqueo final de cuota baja (últimos 2 min del bloque de 15m)
    if min_in_15 >= 13:
        return "NEUTRAL ⚖️", f"Final de bloque ({min_in_15}/15m) - Cuota baja"

    # Señales de Entrada
    is_bull = last['ema9'] > last['ema21'] and last['close'] >= last['open']
    is_bear = last['ema9'] < last['ema21'] and last['close'] <= last['open']

    if is_bull:
        if min_in_15 <= 3:
            return "🔥 COMPRAR UP 🚀", f"Entrada inicio de bloque (min {min_in_15}/15)"
        else:
            return f"⚡ RE-ENTRADA COMPRAR UP 🚀", f"Impulso continuo (min {min_in_15}/15)"

    if is_bear:
        if min_in_15 <= 3:
            return "🔥 COMPRAR DOWN 📉", f"Entrada inicio de bloque (min {min_in_15}/15)"
        else:
            return f"⚡ RE-ENTRADA COMPRAR DOWN 📉", f"Impulso continuo (min {min_in_15}/15)"

    return "NEUTRAL ⚖️", f"Esperando señal clara ({min_in_15}/15m)"

async def coinbase_websocket_listener():
    global candles_1m, current_minute_ticks, last_sent_action
    
    subscribe_msg = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["ticker"]
    }

    while True:
        try:
            async with websockets.connect(COINBASE_WS, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(json.dumps(subscribe_msg))
                print("🟢 Conectado a Coinbase Feed. Procesando...", flush=True)
                
                last_minute = datetime.now().minute
                
                async for msg in ws:
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
                                action, reason = evaluate_signals(candles_1m)
                                
                                # IMPRIMIR OBLIGATORIAMENTE EN CADA MINUTO
                                print(f"[{t_stamp}] BTC: ${close_p:,.2f} | ACCIÓN: {action} ({reason})", flush=True)

                                if "COMPRAR" in action or "CERRAR" in action or "PROFIT" in action:
                                    if action != last_sent_action:
                                        send_discord_alert(action, close_p, reason, t_stamp)
                                        last_sent_action = action

                                current_minute_ticks = []
                            
                            last_minute = now.minute

        except Exception as e:
            print(f"[RECONECTANDO COINBASE]: {e}", flush=True)
            await asyncio.sleep(3)

def run_bot():
    load_initial_candles()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coinbase_websocket_listener())

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
