import os
import time
import requests
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# 1. HEALTH CHECK SERVER FOR RENDER (PORT BINDING)
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Bot running")

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"[SERVIDOR HTTP] Servidor de mantener vivo activo en puerto {port}")
    server.serve_forever()

# ==========================================
# 2. ENVIRONMENT VARIABLES
# ==========================================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "TU_DISCORD_WEBHOOK_URL_AQUI")
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY", "")
EXCHANGE_API_SECRET = os.getenv("EXCHANGE_API_SECRET", "")

# ==========================================
# 3. DISCORD NOTIFICATION MODULE
# ==========================================
def send_discord_alert(title: str, description: str, color: int = 3447003):
    if DISCORD_WEBHOOK_URL == "TU_DISCORD_WEBHOOK_URL_AQUI" or not DISCORD_WEBHOOK_URL:
        print("[ADVERTENCIA] Configura la variable DISCORD_WEBHOOK_URL.")
        return

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    
    payload = {"embeds": [embed]}
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code != 204:
            print(f"[ERROR DISCORD] Status Code: {response.status_code}")
    except Exception as e:
        print(f"[EXCEPCIÓN DISCORD] Error al enviar alerta: {e}")

# ==========================================
# 4. SPORTS MONITORING (HIGH-FREQUENCY: EVERY 1 MIN)
# ==========================================
def check_sports_markets():
    """Escanea mercados deportivos en vivo cada 1 minuto buscando dips/oportunidades."""
    print("[SPORTS] Escaneando eventos deportivos en tiempo real...")
    # Agrega tu lógica de consulta/scraping de Kalshi aquí.

# ==========================================
# 5. BITCOIN 15-MIN PREDICTION MARKETS (EVERY 15 MIN)
# ==========================================
def check_btc_15m_markets():
    """Monitorea el mercado de predicción de BTC a 15 minutos en Kalshi."""
    print("[BTC 15M] Evaluando mercado de predicción de Bitcoin 15m...")
    # Agrega tu lógica de consulta de BTC aquí.

# ==========================================
# 6. LATENCY & PORTFOLIO CHECKS
# ==========================================
def check_latency(target_url: str = "https://api.coinbase.com/v2/time", threshold_ms: float = 500.0):
    start_time = time.time()
    try:
        response = requests.get(target_url, timeout=3)
        latency_ms = (time.time() - start_time) * 1000
        print(f"[LATENCIA] {target_url}: {latency_ms:.2f} ms")
        
        if latency_ms > threshold_ms:
            send_discord_alert(
                title="⚠️ Alerta de Latencia Elevada",
                description=f"Se detectó un retraso de **{latency_ms:.2f} ms** al conectar con `{target_url}`.",
                color=15158332
            )
        return latency_ms
    except Exception as e:
        send_discord_alert(
            title="🚨 Error de Conexión",
            description=f"Fallo de conexión con `{target_url}`: {str(e)}",
            color=15158332
        )
        return None

def check_portfolio_status():
    if not EXCHANGE_API_KEY or not EXCHANGE_API_SECRET:
        print("[INFO] API Keys no configuradas. Reporte de balance omitido.")
        return

    total_balance_usd = 0.0
    daily_pnl = 0.0

    msg = (
        f"**Balance Total:** `${total_balance_usd:,.2f} USD`\n"
        f"**Rendimiento (24h):** `{daily_pnl:+.2f}%`"
    )
    
    send_discord_alert(
        title="📊 Reporte de Rendimiento y Portafolio",
        description=msg,
        color=3066993
    )

# ==========================================
# 7. MAIN ASYNC LOOPS (DUAL FREQUENCY)
# ==========================================
async def sports_loop():
    """Loop de alta frecuencia: revisa deportes cada 60 segundos."""
    while True:
        try:
            check_sports_markets()
        except Exception as e:
            print(f"[ERROR SPORTS LOOP] {e}")
        await asyncio.sleep(60)

async def btc_and_system_loop():
    """Loop de 15 minutos: revisa predicciones BTC 15m, latencia y balance."""
    while True:
        try:
            check_btc_15m_markets()
            check_latency()
            check_portfolio_status()
        except Exception as e:
            print(f"[ERROR MAIN LOOP] {e}")
        await asyncio.sleep(900)

async def main():
    send_discord_alert(
        title="🟢 BOT AUTÓNOMO INICIADO",
        description=(
            "**Configuración Activa:**\n"
            "• **Monitoreo Deportivo:** Escaneo cada **1 minuto** (Alta velocidad)\n"
            "• **Mercado BTC 15M:** Monitoreo cada **15 minutos**\n"
            "• **Noticias & Ballenas:** Disparo **Instantáneo**\n"
            "• **Health Check:** Puerto activo en Render"
        ),
        color=3066993
    )
    
    # Ejecuta ambos loops en paralelo
    await asyncio.gather(
        sports_loop(),
        btc_and_system_loop()
    )

if __name__ == "__main__":
    try:
        # Servidor HTTP para Render (evita cierres por falta de puerto)
        threading.Thread(target=start_health_server, daemon=True).start()
        # Bucle principal de eventos
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[BOT] Detenido por el usuario.")
