import threading
import time
import requests
import pandas as pd
from datetime import datetime
import os
from flask import Flask

# Servidor Flask mínimo para mantener vivo el Web Service en Render
app = Flask(__name__)

@app.route('/')
def health_check():
    return "OK - Bot Kalshi Activo", 200

# ------------------------------------------
# CONFIGURACIÓN DE DISCORD WEBHOOK
# ------------------------------------------
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1533349076593283252/QPKKfcqt0F1I0WcUEnwl5GjVsQTQYL23BvX8FOYM1p4laseCH0iDNPhdfd0VApHafggJ"

last_sent_action = ""

def send_discord_alert(action, price, reason, timestamp):
    if not DISCORD_WEBHOOK_URL:
        print("[DISCORD] ERROR: URL de webhook no encontrada.", flush=True)
        return

    # Definir colores según el tipo de acción
    color = 0x3498DB # Azul por defecto
    if "COMPRAR UP" in action or "CONECTADO" in action:
        color = 0x2ECC71 # Verde
    elif "COMPRAR DOWN" in action:
        color = 0xE74C3C # Rojo
    elif "PROFIT" in action or "CERRAR" in action:
        color = 0xF1C40F # Amarillo

    # Estructura del Embed para Discord
    payload = {
        "username": "Bot Kalshi Signals",
        "embeds": [{
            "title": "🚨 SEÑAL KALSHI BTC 15M",
            "color": color,
            "fields": [
                {"name": "Acción", "value": f"**{action}**", "inline": False},
                {"name": "Precio BTC", "value": f"${price:,.2f}" if price > 0 else "N/A", "inline": True},
                {"name": "Hora", "value": timestamp, "inline": True},
                {"name": "Detalle", "value": reason, "inline": False}
            ],
            "footer": {"text": "Bot Kalshi 15m"}
        }]
    }

    try:
        res = requests.post(
            DISCORD_WEBHOOK_URL, 
            json=payload, 
            headers={"Content-Type": "application/json"}, 
            timeout=5
        )
        print(f"[DISCORD HTTP STATUS]: {res.status_code}", flush=True)
        if res.status_code not in [200, 204]:
            print(f"[DISCORD ERROR RESPUESTA]: {res.text}", flush=True)
    except Exception as e:
        print(f"[ERROR CONEXION DISCORD]: {e}", flush=True)

def fetch_candles():
    """ Obtiene velas de 1m vía REST API directa de Coinbase """
    try:
        url = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=60"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            df = pd.DataFrame(data, columns=['time', 'low', 'high', 'open', 'close', 'volume'])
            df = df.iloc[::-1].reset_index(drop=True)
            df['timestamp'] = pd.to_datetime(df['time'], unit='s').dt.strftime('%H:%M:00')
            return df.tail(30)
    except Exception as e:
        print(f"[ERROR FETCH COINBASE]: {e}", flush=True)
    return None

def evaluate_signals(df_1m):
    if df_1m is None or len(df_1m) < 5:
        return "NEUTRAL ⚖️", "Sin datos suficientes"

    now = datetime.now()
    min_in_15 = now.minute % 15

    # Indicadores Técnicos
    df_1m['ema9'] = df_1m['close'].ewm(span=9, adjust=False).mean()
    df_1m['ema21'] = df_1m['close'].ewm(span=21, adjust=False).mean()

    last = df_1m.iloc[-1]

    # Detección de mechas para salida/take profit
    body = abs(last['close'] - last['open'])
    upper_wick = last['high'] - max(last['close'], last['open'])
    lower_wick = min(last['close'], last['open']) - last['low']

    if upper_wick > (body * 1.3) and upper_wick > 0:
        return "💰 CERRAR / PROFIT (UP)", f"Rechazo bajista en min {min_in_15}/15"
    if lower_wick > (body * 1.3) and lower_wick > 0:
        return "💰 CERRAR / PROFIT (DOWN)", f"Rechazo alcista en min {min_in_15}/15"

    # Bloqueo final del bloque (minutos 13 y 14)
    if min_in_15 >= 13:
        return "NEUTRAL ⚖️", f"Final de bloque ({min_in_15}/15m) - Cuota baja"

    # Dirección de tendencia
    is_bull = last['ema9'] > last['ema21'] and last['close'] >= last['open']
    is_bear = last['ema9'] < last['ema21'] and last['close'] <= last['open']

    if is_bull:
        if min_in_15 <= 3:
            return "🔥 COMPRAR UP 🚀", f"Entrada principal (min {min_in_15}/15)"
        else:
            return f"⚡ RE-ENTRADA COMPRAR UP 🚀", f"Impulso continuo (min {min_in_15}/15)"

    if is_bear:
        if min_in_15 <= 3:
            return "🔥 COMPRAR DOWN 📉", f"Entrada principal (min {min_in_15}/15)"
        else:
            return f"⚡ RE-ENTRADA COMPRAR DOWN 📉", f"Impulso continuo (min {min_in_15}/15)"

    return "NEUTRAL ⚖️", f"Esperando volumen ({min_in_15}/15m)"

def bot_loop():
    global last_sent_action
    print("🚀 Bot iniciado con éxito.", flush=True)
    
    # 1. Notificación inicial de confirmación (Corregida con los 4 parámetros)
    send_discord_alert(
        "🟢 BOT CONECTADO", 
        0, 
        "Bot iniciado correctamente y monitoreando mercado.", 
        datetime.now().strftime('%H:%M:%S')
    )

    # 2. Bucle continuo de monitoreo
    while True:
        try:
            df = fetch_candles()
            if df is not None:
                last_candle = df.iloc[-1]
                close_p = last_candle['close']
                t_stamp = datetime.now().strftime('%H:%M:00')
                
                action, reason = evaluate_signals(df)
                
                print(f"[{t_stamp}] BTC: ${close_p:,.2f} | ACCIÓN: {action} ({reason})", flush=True)

                # Envío de alertas si hay cambio de señal válida
                if "COMPRAR" in action or "CERRAR" in action or "PROFIT" in action:
                    if action != last_sent_action:
                        send_discord_alert(action, close_p, reason, t_stamp)
                        last_sent_action = action

        except Exception as e:
            print(f"[ERROR EN BOT LOOP]: {e}", flush=True)

        time.sleep(30)

if __name__ == "__main__":
    # Arrancar el bot en un hilo secundario
    t = threading.Thread(target=bot_loop, daemon=True)
    t.start()

    # Arrancar el servidor Flask para Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
