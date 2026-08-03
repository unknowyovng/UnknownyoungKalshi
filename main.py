import os
import time
import requests
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

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
# 2. CONFIGURACIÓN Y CREDENCIALES
# ==========================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
KALSHI_API_KEY = os.environ.get("KALSHI_API_KEY", "")  # Agrega tu API Key en Render (Environment)

def get_kalshi_headers():
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    if KALSHI_API_KEY:
        headers["Authorization"] = f"Bearer {KALSHI_API_KEY}"
    return headers

def send_discord_alert(payload):
    if not DISCORD_WEBHOOK_URL:
        print("[DISCORD] Webhook URL not configured. Skipping notification.")
        return
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if res.status_code not in [200, 204]:
            print(f"[DISCORD] Error sending alert: {res.status_code}")
    except Exception as e:
        print(f"[DISCORD] Exception when sending alert: {e}")


# ==========================================
# 3. BITCOIN 15M PREDICTION LOGIC
# ==========================================
def check_btc_15m_markets():
    """
    Monitors Bitcoin 15-minute prediction markets on Kalshi.
    Calculates bullish/bearish streaks and notifies Discord of market shifts.
    """
    try:
        print("[BTC 15M] Evaluating Bitcoin 15m prediction market...")

        url = "https://trading-api.kalshi.com/trade-api/v2/markets"
        params = {
            "limit": 10,
            "series_ticker": "KXBTC15M",
            "status": "open"
        }
        
        # Se agregan los headers con autenticación
        headers = get_kalshi_headers()
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            print(f"[BTC 15M] Error querying Kalshi API: {response.status_code}")
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
        print(f"[BTC 15M] Error during execution: {e}")


# ==========================================
# 4. SPORTS MARKET SCANNER
# ==========================================
def scan_sports_markets():
    try:
        print("[SPORTS] Scanning live sports markets...")
        pass
    except Exception as e:
        print(f"[SPORTS] Error during execution: {e}")


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
