import asyncio
import json
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
        self.wfile.write(b"Bot activo y funcionando en vivo con Feed Coinbase/Kalshi.")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# Forzar salida en vivo en consola
sys.stdout.reconfigure(line_buffering=True)

# WS oficial de Coinbase Pro (Índice directo de Kalshi)
COINBASE_WS = "wss://ws-feed.exchange.coinbase.com"

candles_1m = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
current_minute_ticks = []

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
# EVALUADOR PRO CON ENFOQUE EN KALSHI Y PROFIT RÁPIDO
# ==========================================
def calculate_pro_signal(df_1m):
    if len(df_1m) < 15:
        return "NEUTRAL ⚖️", "ACUMULANDO VELAS DE COINBASE PARA 15M"

    df_15m = resample_candles(df_1m, '15min')

    df_1m['ema9'] = df_1m['close'].ewm(span=9, adjust=False).mean()
    df_1m['ema21'] = df_1m['close'].ewm(span=21, adjust=False).mean()
    
    avg_vol = df_1m['volume'].tail(10).mean()
    last_1m = df_1m.iloc[-1]
    
    high_volume = last_1m['volume'] > (avg_vol * 2.0)

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

    # --- REGLAS DE SALIDA PREVENTIVA / TOMAR PROFIT ---
    if upper_wick > (body * 1.3) and upper_wick > 0:
        return "💰 CERRAR / TOMAR PROFIT (UP)", "RECHAZO DE ALTOS EN COINBASE - ASEGURA PROFIT"
    
    if lower_wick > (body * 1.3) and lower_wick > 0:
        return "💰 CERRAR / TOMAR PROFIT (DOWN)", "RECHAZO DE BAJOS EN COINBASE - ASEGURA PROFIT"

    # --- ENTRADAS FILTRADAS ---
    ema_bull_1m = last_1m['ema9'] > last_1m['ema21']
    ema_bear_1m = last_1m['ema9'] < last_1m['ema21']
    green_candle = last_1m['close'] > last_1m['open']
    red_candle = last_1m['close'] < last_1m['open']

    if ema_bull_1m and green_candle:
        if trend_15m == "ALCISTA" or high_volume:
            conf = "CONFIRMADO EN 15M (RETIRARSE CON PROFIT)"
            return "COMPRAR UP 🚀", conf
        else:
            return "NEUTRAL ⚖️", "1M ALCISTA PERO 15M SIN CONFIRMACIÓN"

    if ema_bear_1m and red_candle:
        if trend_15m == "BAJISTA" or high_volume:
            conf = "CONFIRMADO EN 15M (RETIRARSE CON PROFIT)"
            return "COMPRAR DOWN 📉", conf
        else:
            return "NEUTRAL ⚖️", "1M BAJISTA PERO 15M SIN CONFIRMACIÓN"

    return "NEUTRAL ⚖️", "MERCADO SIN TENDENCIA EN COINBASE"

# ==========================================
# FEED COINBASE WEBSOCKET (ÍNDICE REAL KALSHI)
# ==========================================
async def coinbase_websocket_listener():
    global candles_1m, current_minute_ticks
    
    subscribe_msg = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["ticker"]
    }

    while True:
        try:
            async with websockets.connect(COINBASE_WS) as ws:
                await ws.send(json.dumps(subscribe_msg))
                print("🟢 Conectado al Feed de Coinbase (Sincronización 1:1 con Kalshi)...", flush=True)
                
                last_minute = datetime.now().minute
                
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    if data.get('type') == 'ticker' and 'price' in data:
                        price = float(data['price'])
                        size = float(data.get('last_size', 0))
                        now = datetime.now()
                        
                        current_minute_ticks.append({'price': price, 'size': size})
                        
                        # Al cambiar de minuto, se consolida la vela oficial
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
                                action, reason = calculate_pro_signal(candles_1m)
                                
                                print(f"[{t_stamp}] BTC Index (Kalshi): ${close_p:,.2f} | Apertura: ${open_p:,.2f} | ACCIÓN: {action} ({reason})", flush=True)

                                current_minute_ticks = []
                            
                            last_minute = now.minute

        except Exception as e:
            print(f"[RECONECTANDO COINBASE]: {e}", flush=True)
            await asyncio.sleep(5)

# ==========================================
# BUCLE PRINCIPAL
# ==========================================
async def main():
    threading.Thread(target=run_http_server, daemon=True).start()
    print("🚀 BOT CON FEED DE PRECISIÓN KALSHI / COINBASE INICIADO...", flush=True)
    await coinbase_websocket_listener()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot detenido.", flush=True)
