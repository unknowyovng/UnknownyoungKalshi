import asyncio
import json
import os
import sys
import websockets
import pandas as pd
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_GET(self):
        self.do_HEAD()
        self.wfile.write(b"Bot activo en Modo Maximas Entradas de Intervalo (15m/Kalshi).")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

sys.stdout.reconfigure(line_buffering=True)

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
# EVALUADOR DE MULTI-ENTRADAS POR INTERVALO
# ==========================================
def calculate_interval_signals(df_1m):
    if len(df_1m) < 5:
        return "NEUTRAL ⚖️", "RECOLECTANDO VELAS INICIALES"

    now = datetime.now()
    minute_of_hour = now.minute
    
    # Identificar en qué intervalo de 15 min estamos (0, 15, 30, 45)
    interval_start_min = (minute_of_hour // 15) * 15
    minute_in_interval = minute_of_hour - interval_start_min  # Va de 0 a 14

    df_15m = resample_candles(df_1m, '15min')

    df_1m['ema9'] = df_1m['close'].ewm(span=9, adjust=False).mean()
    df_1m['ema21'] = df_1m['close'].ewm(span=21, adjust=False).mean()
    
    last_1m = df_1m.iloc[-1]
    
    # Evaluación de Tendencia Base de 15 Minutos
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

    # --- ALERTAS DE SALIDA Y PROFIT (RECHAZO) ---
    if upper_wick > (body * 1.3) and upper_wick > 0:
        return "💰 CERRAR / TOMAR PROFIT (UP)", f"AGOTAMIENTO EN MINUTO {minute_in_interval}/15 DE BLOQUE"
    
    if lower_wick > (body * 1.3) and lower_wick > 0:
        return "💰 CERRAR / TOMAR PROFIT (DOWN)", f"AGOTAMIENTO EN MINUTO {minute_in_interval}/15 DE BLOQUE"

    # --- LÓGICA DE MAXIMIZACIÓN DE ENTRADAS ---
    ema_bull = last_1m['ema9'] > last_1m['ema21']
    ema_bear = last_1m['ema9'] < last_1m['ema21']
    green = last_1m['close'] > last_1m['open']
    red = last_1m['close'] < last_1m['open']

    # Fase 1: Inicio de Intervalo (Minuto 0 a 3) -> Entrada de Alta Prioridad
    if minute_in_interval <= 3:
        if ema_bull and green:
            return "🔥 INICIO BLOQUE: COMPRAR UP 🚀", f"APERTURA INTERVALO {interval_start_min}m"
        elif ema_bear and red:
            return "🔥 INICIO BLOQUE: COMPRAR DOWN 📉", f"APERTURA INTERVALO {interval_start_min}m"

    # Fase 2: Mitad de Intervalo (Minuto 4 a 10) -> Re-entrada / Scalping
    elif 4 <= minute_in_interval <= 10:
        if ema_bull and green and trend_15m == "ALCISTA":
            return "⚡ RE-ENTRADA: COMPRAR UP 🚀", f"IMPULSO MID-INTERVALO ({minute_in_interval}m)"
        elif ema_bear and red and trend_15m == "BAJISTA":
            return "⚡ RE-ENTRADA: COMPRAR DOWN 📉", f"IMPULSO MID-INTERVALO ({minute_in_interval}m)"

    # Fase 3: Final del Intervalo (Minuto 11 a 14) -> Filtrado estricto para evitar atrapadas
    elif minute_in_interval >= 11:
        if ema_bull and green and (last_1m['close'] > df_1m['high'].tail(5).max()):
            return "🎯 ULTIMO IMPULSO: COMPRAR UP 🚀", "ROMPIMIENTO DE CERRADO DE BLOQUE"
        elif ema_bear and red and (last_1m['close'] < df_1m['low'].tail(5).min()):
            return "🎯 ULTIMO IMPULSO: COMPRAR DOWN 📉", "ROMPIMIENTO DE CERRADO DE BLOQUE"
        else:
            return "⚠️ ZONA FINAL DE BLOQUE", "PREPARANDO PRÓXIMO CONTRATO DE 15M"

    return "NEUTRAL ⚖️", f"SIN PATRÓN EN MINUTO {minute_in_interval}/15"

# ==========================================
# FEED COINBASE WEBSOCKET
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
                print("🟢 Conectado al Feed de Coinbase (Modo Máxima Frecuencia 15m)...", flush=True)
                
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
    print("🚀 BOT DE MÁXIMAS ENTRADAS POR INTERVALO INICIADO...", flush=True)
    await coinbase_websocket_listener()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot detenido.", flush=True)
