import os
import time
import base64
import requests
import datetime
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization

# ==========================================
# 1. HTTP SERVER FOR RENDER HEALTH CHECKS
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Bot is running")

    def log_message(self, format, *args):
        return

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"[SERVER] Web server started on port {port}")
    server.serve_forever()

server_thread = threading.Thread(target=run_http_server, daemon=True)
server_thread.start()


# ==========================================
# 2. CONFIGURACIÓN Y AUTENTICACIÓN RSA KALSHI
# ==========================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
KALSHI_KEY_ID = os.environ.get("KALSHI_KEY_ID", "")
KALSHI_PRIVATE_KEY_PEM = os.environ.get("KALSHI_PRIVATE_KEY", "")

# Nuevo endpoint de la API de Kalshi
KALSHI_BASE_URL = "https://api.elections.kalshi.com"

def get_kalshi_headers(method: str, path: str) -> dict:
    if not KALSHI_KEY_ID or not KALSHI_PRIVATE_KEY_PEM:
        print("[AUTH WARNING] KALSHI_KEY_ID o KALSHI_PRIVATE_KEY no configurados.")
        return {"Content-Type": "application/json"}

    try:
        formatted_pem = KALSHI_PRIVATE_KEY_PEM.replace('\\n', '\n').strip()
        timestamp = str(int(time.time() * 1000))
        
        msg_string = f"{timestamp}{method.upper()}{path}"
        msg_bytes = msg_string.encode('utf-8')

        private_key = serialization.load_pem_private_key(
            formatted_pem.encode('utf-8'),
            password=None
        )

        signature = private_key.sign(
            msg_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )

        signature_b64 = base64.b64encode(signature).decode('utf-8')

        return {
            "KALSHI-ACCESS-KEY": KALSHI_KEY_ID.strip(),
            "KALSHI-ACCESS-SIGNATURE": signature_b64,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json"
        }
    except Exception as e:
        print(f"[AUTH ERROR] Error firmando la petición: {e}")
        return {"Content-Type": "application/json"}


def send_discord_alert(payload):
    if not DISCORD_WEBHOOK_URL:
        print("[DISCORD] Webhook URL no configurada.")
        return
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if res.status_code not in [200, 204]:
            print(f"[DISCORD] Error enviando alerta: {res.status_code}")
    except Exception as e:
        print(f"[DISCORD] Excepción enviando alerta: {e}")


# ==========================================
# 3. BITCOIN 15M PREDICTION LOGIC
# ==========================================
def check_btc_15m_markets():
    try:
        print("[BTC 15M] Evaluating Bitcoin 15m prediction market...")

        path = "/trade-api/v2/markets"
        url = f"{KALSHI_BASE_URL}{path}"
        params = {
            "limit": 10,
            "series_ticker": "KXBTC15M",
            "status": "open"
        }

        headers = get_kalshi_headers("GET", path)

        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            print(f"[BTC 15M] Error querying Kalshi API: {response.status_code} - {response.text}")
            return

        data = response.json()
        markets = data.get("markets", [])

        if not markets:
            print("[BTC 15M] No active BTC 15m markets found.")
            return

        current_market = markets[0]
        ticker = current_market.get("ticker")
        yes_bid = current_market.get("yes_bid", 0)
        yes_ask = current_market.get("yes_ask", 0)
        last_price = current_market.get("last_price", 50)
        
        prob_yes = last_price

        # Streak & Direction Analysis
        estado_mercado = "NEUTRO"
        emoji = "⚖️"

        if prob_yes >= 65:
            estado_mercado = "RACHA ALCISTA (BULLISH)"
            emoji = "🚀"
        elif prob_yes <= 35:
            estado_mercado = "RACHA BAJISTA (BEARISH)"
            emoji = "🔻"

        if estado_mercado != "NEUTRO":
            mensaje_discord = {
                "embeds": [{
                    "title": f"{emoji} Alerta BTC 15M - Mercado Kalshi",
                    "description": f"**Ticker:** `{ticker}`\n"
                                   f"**Estado/Racha:** **{estado_mercado}**\n"
                                   f"**Probabilidad YES:** `{prob_yes}%`\n"
                                   f"**Bid/Ask:** `{yes_bid}% / {yes_ask}%`",
                    "color": 3066993 if "ALCISTA" in estado_mercado else 15158332,
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }]
            }
            send_discord_alert(mensaje_discord)
            print(f"[BTC 15M] Notification sent to Discord: {estado_mercado} ({prob_yes}%)")

    except Exception as e:
        print(f"[BTC 15M] Error durante la ejecución: {e}")


# ==========================================
# 4. SPORTS MARKET SCANNER
# ==========================================
def scan_sports_markets():
    try:
        print("[SPORTS] Scanning live sports markets...")
        pass
    except Exception as e:
        print(f"[SPORTS] Error durante la ejecución: {e}")


# ==========================================
# 5. MAIN EXECUTION LOOP
# ==========================================
if __name__ == "__main__":
    print("[BOT] Starting automated trading monitor...")
    cycle_counter = 0

    while True:
        try:
            scan_sports_markets()

            if cycle_counter % 3 == 0:
                check_btc_15m_markets()

            cycle_counter += 1
            time.sleep(60)

        except KeyboardInterrupt:
            print("[BOT] Shutting down gracefully...")
            break
        except Exception as e:
            print(f"[BOT] Unexpected error in main loop: {e}")
            time.sleep(60)
