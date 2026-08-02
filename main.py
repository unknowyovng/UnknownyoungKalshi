import asyncio
import json
import time
import os
import sys
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

# Buffers de datos
candles_1m = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

def resample_candles(df, timeframe='15min'):
    if df.empty or len(df) < 15:
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

# ==========================================
# EVALUADOR PRO CON ENFOQUE EN 15M Y PROFIT RÁPIDO
# ==========================================
def calculate_pro_signal(df_1m):
    if len(df_1m) < 15:
        return "NEUTRAL ⚖️", "ACUMULANDO VELAS PARA ANÁLISIS DE 15 MINUTOS"

    # 1. Resample a 5m y 15m
    df_5m = resample_candles(df_1m, '5min')
    df_15m = resample_candles(df_1m, '15min')

    # Cálculos en 1m
    df_1m['ema9'] = df_1m['close'].ewm(span=9, adjust=False).mean()
    df_1m['ema21'] = df_1m['close'].ewm(span=21, adjust=False).mean()
    
    avg_vol = df_1m['volume'].tail(10).mean()
    last_1m = df_1m.iloc[-1]
    
    # Detección de Ballena / Volumen Inusual
    high_volume = last_1m['volume'] > (avg_vol * 2.2)

    # Evaluación de Tendencia de 15 Minutos (Tendencia Madre)
    trend_15m = "NEUTRAL"
    if not df_15m.empty and len(df_15m) >= 2:
        df_15m['ema9'] = df_15m['close'].ewm(span=9, adjust=False).mean()
        df_15m['ema21'] = df_15m['close'].ewm(span=21, adjust=False).mean()
        last_15m = df_15m.iloc[-1]
        if last_15m['ema9'] > last_15m['ema21']:
            trend_15m = "ALCISTA"
        elif last_15m['ema9'] < last_15m['ema21']:
            trend_15m = "BAJISTA"

    # Patrón de la vela actual (Sombra / Agotamiento)
    body = abs(last_1m['close'] - last_1m['open'])
    upper_wick = last_1m['high'] - max(last_1m['close'], last_1m['open'])
    lower_wick = min(last_1m['close'], last_1m['open']) - last_1m['low']

    # --- REGLAS DE SALIDA Y PROFIT (RETIRARSE TEMPRANO) ---
    if upper_wick > (body * 1.3) and upper_wick > 0:
        return "💰 CERRAR / TOMAR PROFIT (UP)", "AGOTAMIENTO ALCISTA - ASEGURA GANANCIA"
    
    if lower_wick > (body * 1.3) and lower_wick > 0:
        return "💰 CERRAR / TOMAR PROFIT (DOWN)", "AGOTAMIENTO BAJISTA - ASEGURA GANANCIA"

    # --- ENTRADAS FILTRADAS CON TENDENCIA 15M ---
    ema_bull_1m = last_1m['ema9'] > last_1m['ema21']
    ema_bear_1m = last_1m['ema9'] < last_1m['ema21']
    green_candle = last_1m['close'] > last_1m['open']
    red_candle = last_1m['close'] < last_1m['open']

    # Entrada UP (Solo si 15m respalda o hay volumen masivo)
    if ema_bull_1m and green_candle:
        if trend_15m == "ALCISTA" or high_volume:
            conf = "DIRECCIÓN CONFIRMADA (MANTENER TIEMPO)" if high_volume else "ALINEADO CON 15M (BUSCAR PROFIT RÁPIDO)"
            return "COMPRAR UP 🚀", conf
        else:
            return "NEUTRAL ⚖️", "1M ALCISTA PERO CONFLICTO CON TENDENCIA 15M"

    # Entrada DOWN (Solo si 15m respalda o hay volumen masivo)
    if ema_bear_1m and red_candle:
        if trend_15m == "BAJISTA" or high_volume:
            conf = "DIRECCIÓN CONFIRMADA (MANTENER TIEMPO)" if high_volume else "ALINEADO CON 15M (BUSCAR PROFIT RÁPIDO)"
            return "COMPRAR DOWN 📉", conf
        else:
            return "NEUTRAL ⚖️", "1M BAJISTA PERO CONFLICTO CON TENDENCIA 15M"

    return "NEUTRAL ⚖️", "MERCADO EN RANGO / ESPERANDO CONFIRMACIÓN"

# ==========================================
# FEED EN TIEMPO REAL
# ==========================================
async def btc_websocket_listener():
    global candles_1m
    while True:
        try:
            async with websockets.connect(BINANCE_WS) as ws:
                print("🟢 Conectado al Feed Estratégico (15M / Scalping Profit)...", flush=True)
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
                        
                        action, reason = calculate_pro_signal(candles_1m)
                        
                        print(f"[{t_stamp}] BTC: ${close_p:,.2f} | Apertura: ${open_p:,.2f} | ACCIÓN: {action} ({reason})", flush=True)

        except Exception as e:
            print(f"[RECONECTANDO WEBSOCKET]: {e}", flush=True)
            await asyncio.sleep(5)

# ==========================================
# BUCLE PRINCIPAL
# ==========================================
async def main():
    threading.Thread(target=run_http_server, daemon=True).start()
    print("🚀 BOT ESTRATÉGICO 15M + PROFIT RÁPIDO INICIADO...", flush=True)
    await btc_websocket_listener()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot detenido.", flush=True)
