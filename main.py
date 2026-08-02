import asyncio
import json
import time
import base64
import os
import sys
import requests
import websockets
import pandas as pd
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Servidor HTTP ficticio para Render (Compatible con UptimeRobot)
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_GET(self):
        self.do_HEAD()
        self.wfile.write(b"Bot activo y funcionando en vivo.")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# Forzar salida en vivo en consola
sys.stdout.reconfigure(line_buffering=True)

BINANCE_WS = "wss://stream.binance.us:9443/ws/btcusdt@kline_1m"
candles_1m = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

# ==========================================
# EVALUADOR TÉCNICO CON ALERTA DE RETROCESO
# ==========================================
def calculate_signal(df):
    if len(df) < 5:
        return "NEUTRAL ⚖️", "ESPERANDO MÁS VELAS"

    # Medias Móviles Exponenciales (EMA 9 y EMA 21)
    df['ema_fast'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=21, adjust=False).mean()
    
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Criterios principales de entrada
    ema_bullish = last['ema_fast'] > last['ema_slow']
    ema_bearish = last['ema_fast'] < last['ema_slow']
    candle_green = last['close'] > last['open']
    candle_red = last['close'] < last['open']

    # --- DETECTOR DE RETROCESO / AGOTAMIENTO ---
    candle_body = abs(last['close'] - last['open'])
    upper_wick = last['high'] - max(last['close'], last['open'])
    lower_wick = min(last['close'], last['open']) - last['low']

    # Alerta 1: Agotamiento Alcista (Sombra superior larga en tendencia alcista)
    if ema_bullish and upper_wick > (candle_body * 1.5) and upper_wick > 0:
        return "🚨 VENDER/SALIR DE UP", "RECHAZO DE PRECIOS ALTOS (POSIBLE RETROCESO)"

    # Alerta 2: Agotamiento Bajista (Sombra inferior larga en tendencia bajista)
    if ema_bearish and lower_wick > (candle_body * 1.5) and lower_wick > 0:
        return "🚨 VENDER/SALIR DE DOWN", "RECHAZO DE PRECIOS BAJOS (POSIBLE REBOTE)"

    # --- SEÑALES ESTÁNDAR DE ENTRADA ---
    if ema_bullish and candle_green:
        return "COMPRAR UP 🚀", "TENDENCIA ALCISTA CONFIRMADA"
    elif ema_bearish and candle_red:
        return "COMPRAR DOWN 📉", "TENDENCIA BAJISTA CONFIRMADA"
    else:
        return "NEUTRAL ⚖️", "MERCADO SIN DIRECCIÓN CLARA"

# ==========================================
# FEED EN TIEMPO REAL (Binance WebSocket)
# ==========================================
async def btc_websocket_listener():
    global candles_1m
    while True:
        try:
            async with websockets.connect(BINANCE_WS) as ws:
                print("🟢 Conectado al Feed de Binance con Alerta de Retroceso...", flush=True)
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    kline = data.get('k', {})
                    is_candle_closed = kline.get('x', False)

                    if is_candle_closed:
                        open_p = float(kline['o'])
                        high_p = float(kline['h'])
                        low_p = float(kline['l'])
                        close_p = float(kline['c'])
                        vol = float(kline['v'])
                        t_stamp = datetime.now().strftime('%H:%M:%S')

                        new_row = pd.DataFrame([{
                            'timestamp': t_stamp, 'open': open_p, 
                            'high': high_p, 'low': low_p, 
                            'close': close_p, 'volume': vol
                        }])
                        
                        candles_1m = pd.concat([candles_1m, new_row], ignore_index=True)
                        
                        action, reason = calculate_signal(candles_1m)
                        
                        print(f"[{t_stamp}] BTC: ${close_p:,.2f} | Apertura: ${open_p:,.2f} | ACCIÓN: {action} ({reason})", flush=True)

        except Exception as e:
            print(f"[RECONECTANDO WEBSOCKET]: {e}", flush=True)
            await asyncio.sleep(5)

# ==========================================
# BUCLE PRINCIPAL
# ==========================================
async def main():
    threading.Thread(target=run_http_server, daemon=True).start()
    print("🚀 BOT CON PROTECCIÓN CONTRA RETROCESOS INICIADO...", flush=True)
    await btc_websocket_listener()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot detenido.", flush=True)
