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
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

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

# ==========================================
# CONFIGURACIÓN Y CREDENCIALES
# ==========================================
BINANCE_WS = "wss://stream.binance.us:9443/ws/btcusdt@trade"
KALSHI_BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"
KALSHI_API_KEY_ID = "TU_KALSHI_KEY_ID"
PRIVATE_KEY_PATH = "private_key.pem"
NEWS_API_URL = "https://cryptopanic.com/api/v1/posts/?auth_token=TU_TOKEN&currencies=BTC"

WHALE_THRESHOLD_USD = 100000 

candles_1m = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
candles_5m = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
ticks_buffer = []

# ==========================================
# 1. AUTENTICACIÓN Y ÓRDENES EN KALSHI (RSA)
# ==========================================
def load_private_key(file_path):
    try:
        with open(file_path, "rb") as key_file:
            return serialization.load_pem_private_key(key_file.read(), password=None)
    except Exception as e:
        print(f"[ERROR CLAVE KALSHI]: No se pudo cargar {file_path} -> {e}", flush=True)
        return None

def sign_kalshi_request(private_key, method, path, timestamp):
    path_clean = path.split('?')[0]
    msg = f"{timestamp}{method}{path_clean}"
    signature = private_key.sign(
        msg.encode('utf-8'),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def send_kalshi_order(ticker, side, count=1, action='buy'):
    path = "/trade-api/v2/portfolio/orders"
    timestamp = str(int(time.time() * 1000))
    private_key = load_private_key(PRIVATE_KEY_PATH)
    
    if not private_key:
        print("[KALSHI OMITIDO]: Sin clave RSA configurada.", flush=True)
        return

    sig = sign_kalshi_request(private_key, "POST", path, timestamp)

    headers = {
        "KALSHI-ACCESS-KEY": KALSHI_API_KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "Content-Type": "application/json"
    }

    payload = {
        "ticker": ticker,
        "action": action,
        "type": "market",
        "side": side,
        "count": count
    }

    try:
        res = requests.post(KALSHI_BASE_URL + path, headers=headers, json=payload)
        print(f"[KALSHI ORDER] Respuesta ({res.status_code}): {res.json()}", flush=True)
    except Exception as e:
        print(f"[ERROR KALSHI ORDER]: {e}", flush=True)

# ==========================================
# 2. EVALUADOR DE NOTICIAS
# ==========================================
async def fetch_latest_news():
    try:
        res = requests.get(NEWS_API_URL, timeout=5)
        if res.status_code == 200:
            posts = res.json().get('results', [])
            if posts:
                latest = posts[0]
                votes = latest.get('votes', {})
                bullish = votes.get('bullish', 0)
                bearish = votes.get('bearish', 0)
                print(f"[NOTICIAS 🗞️] '{latest.get('title', '')[:50]}...' | Bullish: {bullish} - Bearish: {bearish}", flush=True)
                return "BULL" if bullish > bearish else ("BEAR" if bearish > bullish else "NEUTRAL")
    except Exception as e:
        print(f"[ERROR NOTICIAS]: {e}", flush=True)
    return "NEUTRAL"

# ==========================================
# 3. GENERADOR DE SEÑALES TÉCNICAS
# ==========================================
def generate_signals(df, timeframe="1m"):
    if len(df) < 2:
        return "NEUTRAL"

    df['ema_fast'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=21, adjust=False).mean()
    
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    signal = "NEUTRAL"
    if prev_row['ema_fast'] <= prev_row['ema_slow'] and last_row['ema_fast'] > last_row['ema_slow']:
        signal = "BULLISH"
    elif prev_row['ema_fast'] >= prev_row['ema_slow'] and last_row['ema_fast'] < last_row['ema_slow']:
        signal = "BEARISH"

    return signal

# ==========================================
# 4. FEED EN TIEMPO REAL (Binance WebSocket)
# ==========================================
async def btc_websocket_listener():
    global ticks_buffer
    while True:
        try:
            async with websockets.connect(BINANCE_WS) as ws:
                print("🟢 Conectado al Feed en Tiempo Real de Binance.US (BTC/USDT)...", flush=True)
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    price = float(data['p'])
                    quantity = float(data['q'])
                    usd_val = price * quantity
                    is_seller = data['m']

                    if usd_val >= WHALE_THRESHOLD_USD:
                        action = "🔴 VENTA BALLENA" if is_seller else "🟢 COMPRA BALLENA"
                        print(f"[BALLENA 🐋] {action} | Monto: ${usd_val:,.2f} | BTC: ${price:,.2f}", flush=True)

                    ticks_buffer.append({'timestamp': time.time(), 'price': price, 'volume': quantity})
        except Exception as e:
            print(f"[RECONECTANDO WEBSOCKET]: {e}", flush=True)
            await asyncio.sleep(5)

# ==========================================
# 5. CONSTRUCTOR DE VELAS Y EVALUADOR
# ==========================================
async def candle_builder_loop():
    global ticks_buffer, candles_1m, candles_5m
    
    while True:
        await asyncio.sleep(60)
        
        if not ticks_buffer:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Esperando marcas de tiempo...", flush=True)
            continue
            
        df_ticks = pd.DataFrame(ticks_buffer)
        ticks_buffer = []
        
        c_open = df_ticks['price'].iloc[0]
        c_high = df_ticks['price'].max()
        c_low = df_ticks['price'].min()
        c_close = df_ticks['price'].iloc[-1]
        c_vol = df_ticks['volume'].sum()
        
        new_row = pd.DataFrame([{
            'timestamp': time.time(), 'open': c_open, 'high': c_high, 
            'low': c_low, 'close': c_close, 'volume': c_vol
        }])
        
        candles_1m = pd.concat([candles_1m, new_row], ignore_index=True)
        
        sig_1m = generate_signals(candles_1m, timeframe="1m")
        print(f"[VELA 1M 📊] {datetime.now().strftime('%H:%M:%S')} | Cierre BTC: ${c_close:,.2f} | Señal: {sig_1m}", flush=True)
        
        if len(candles_1m) % 5 == 0:
            sub = candles_1m.iloc[-5:]
            row_5m = pd.DataFrame([{
                'timestamp': time.time(),
                'open': sub['open'].iloc[0],
                'high': sub['high'].max(),
                'low': sub['low'].min(),
                'close': sub['close'].iloc[-1],
                'volume': sub['volume'].sum()
            }])
            candles_5m = pd.concat([candles_5m, row_5m], ignore_index=True)
            
            sig_5m = generate_signals(candles_5m, timeframe="5m")
            news_sentiment = await fetch_latest_news()
            
            if sig_1m == "BULLISH" and sig_5m == "BULLISH" and news_sentiment != "BEAR":
                print("[EJECUCIÓN 🚀] Confirmación Alcista (1m+5m) -> Comprando 'YES' en Kalshi", flush=True)
            elif sig_1m == "BEARISH" and sig_5m == "BEARISH" and news_sentiment != "BULL":
                print("[EJECUCIÓN 📉] Confirmación Bajista (1m+5m) -> Comprando 'NO' en Kalshi", flush=True)

# ==========================================
# 6. BUCLE PRINCIPAL
# ==========================================
async def main():
    threading.Thread(target=run_http_server, daemon=True).start()
    print("🚀 BOT INICIADO CORRECTAMENTE Y ESCUCHANDO A BINANCE...", flush=True)
    
    await asyncio.gather(
        btc_websocket_listener(),
        candle_builder_loop()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot detenido.", flush=True)
