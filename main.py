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
    if "COMPRAR UP" in action or "INICIO" in action:
        color = 0x2ECC71
    elif "COMPRAR DOWN" in action:
        color = 0xE74C3C
    elif "PROFIT" in action or "CERRAR" in action:
        color = 0xF1C40F

    embed = {
        "title": "🚨 SEÑAL KALSHI BTC (DINÁMICA 15M)",
        "color": color,
        "fields": [
            {"name": "Acción", "value": f"**{action}**", "inline": False},
            {"name": "Precio BTC Kalshi", "value": f"${price:,.2f}", "inline": True},
            {"name": "Hora", "value": timestamp, "inline": True},
            {"name": "Detalle / Motivo", "value": reason, "inline": False}
        ],
        "footer": {"text": "Bot Multiopero 15m | Entradas continuas Min 0-12"}
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

def calculate_interval_signals(df_1m):
    if len(df_1m) < 5:
        return "NEUTRAL ⚖️", "RECOLECTANDO VELAS INICIALES"

    now = datetime.now()
    minute_of_hour = now.minute
    interval_start_min = (minute_of_hour // 15) * 15
    minute_in_interval = minute_of_hour - interval_start_min

    # Cálculo de EMAs de reacción rápida
    df_1m['ema9'] = df_1m['close'].ewm(span=9, adjust=False).mean()
    df_1m['ema21'] = df_1m['close'].ewm(span=21, adjust=False).mean()
    
    last_1m = df_1m.iloc[-1]
    prev_1m = df_1m.iloc[-2]

    # Medición de cuerpo y mechas
    body = abs(last_1m['close'] - last_1m['open'])
    upper_wick = last_1m['high'] - max(last_1m['close'], last_1m['open'])
    lower_wick = min(last_1m['close'], last_1m['open']) - last_1m['low']

    # 1. ALERTAS DE CIERRE Y TOMAR GANANCIA (En cualquier minuto)
    if upper_wick > (body * 1.4) and upper_wick > 0:
        return "💰 CERRAR / TOMAR PROFIT (UP)", f"Rechazo bajista (Mecha superior) en min {minute_in_interval}/15"
    
    if lower_wick > (body * 1.4) and lower_wick > 0:
        return "💰 CERRAR / TOMAR PROFIT (DOWN)", f"Rechazo alcista (Mecha inferior) en min {minute_in_interval}/15"

    # 2. BLOQUEO FINAL DE CUOTAS (Últimos 2 minutos del bloque de 15m)
    if minute_in_interval >= 13:
        return "NEUTRAL ⚖️", f"CIERRE DE BLOQUE ({minute_in_interval}/15m) - Cuotas extremadamente bajas en Kalshi"

    # 3. CONDICIONES TÉCNICAS
    ema_bull = last_1m['ema9'] > last_1m['ema21']
    ema_bear = last_1m['ema9'] < last_1m['ema21']
    green = last_1m['close'] > last_1m['open']
    red = last_1m['close'] < last_1m['open']
    momentum_up = last_1m['close'] > prev_1m['close']
    momentum_down = last_1m['close'] < prev_1m['close']

    # 4. ENTRADAS Y MULTI-OPERACIONES (Minutos 0 a 12)
    if minute_in_interval <= 3:
        if ema_bull and green:
            return "🔥 ENTRADA PRINCIPAL: COMPRAR UP 🚀", f"Inicio de bloque ({minute_in_interval}m/15m) - Cuota óptima"
        elif ema_bear and red:
            return "🔥 ENTRADA PRINCIPAL: COMPRAR DOWN 📉", f"Inicio de bloque ({minute_in_interval}m/15m) - Cuota óptima"

    elif 4 <= minute_in_interval <= 12:
        if ema_bull and green and momentum_up:
            return f"⚡ RE-ENTRADA #{minute_in_interval}: COMPRAR UP 🚀", f"Impulso continuo en min {minute_in_interval}/15"
        elif ema_bear and red and momentum_down:
            return f"⚡ RE-ENTRADA #{minute_in_interval}: COMPRAR DOWN 📉", f"Impulso continuo en min {minute_in_interval}/15"

    return "NEUTRAL ⚖️", f"Consolidando / Sin impulso claro ({minute_in_interval}/15m)"

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
                print("🟢 Conectado a Coinbase Feed. Procesando ticks...", flush=True)
                
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

                                if "COMPRAR" in action or "CERRAR" in action or "PROFIT" in action or "ENTRADA" in action:
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
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coinbase_websocket_listener())

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
