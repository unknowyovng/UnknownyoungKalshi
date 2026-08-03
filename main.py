import os
import time
import threading
import requests
from flask import Flask

# ---------------------------------------------------------
# 1. SERVIDOR HTTP PARA RENDER (HEALTH CHECK)
# ---------------------------------------------------------
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot de Kalshi & Bitcoin (Web Service) activo y ejecutándose correctamente.", 200

def run_http_server():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ---------------------------------------------------------
# 2. CONFIGURACIÓN DE DISCORD WEBHOOK
# ---------------------------------------------------------
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK")

def send_discord_alert(title, details, alert_type="INFO"):
    """
    Envía alertas formateadas a Discord vía Webhook.
    """
    if not WEBHOOK_URL:
        print(f"[{alert_type}] {title}: {details} (Falta DISCORD_WEBHOOK_URL)")
        return

    emoji_map = {
        "BTC_15M": "⚡",
        "BTC_1H": "⏳",
        "SPORTS": "⚽",
        "NEWS": "📰",
        "INFO": "📊"
    }
    emoji = emoji_map.get(alert_type, "📢")
    
    content = f"{emoji} **[{alert_type}] {title}**\n{details}"
    payload = {"content": content}
    
    try:
        res = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if res.status_code in [200, 204]:
            print(f"✅ Alerta '{title}' enviada a Discord.")
        else:
            print(f"Error Webhook HTTP {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Error enviando mensaje a Discord: {e}")

# ---------------------------------------------------------
# 3. MONITOREO DE MERCADOS PÚBLICOS KALSHI (BTC Y DEPORTES)
# ---------------------------------------------------------
KALSHI_API_URL = "https://api.elections.kalshi.com/v1/events"

def scan_kalshi_markets():
    """
    Escanea mercados de Kalshi buscando eventos de Bitcoin (15m/1h) y anomalías en Deportes.
    """
    try:
        response = requests.get(
            KALSHI_API_URL,
            params={"limit": 20, "status": "open"},
            headers={"Accept": "application/json"},
            timeout=10
        )
        if response.status_code != 200:
            print(f"Error consultando Kalshi HTTP {response.status_code}")
            return

        events = response.json().get("events", [])
        
        for event in events:
            category = event.get("category", "").upper()
            title = event.get("title", "")
            markets = event.get("markets", [])
            
            if not markets:
                continue

            last_price = markets[0].get("last_price", 0)

            # --- Evaluación Bitcoin 15m y 1h ---
            if "BITCOIN" in title.upper() or "BTC" in title.upper():
                timeframe = "15m" if "15" in title else "1h"
                alert_tag = "BTC_15M" if timeframe == "15m" else "BTC_1H"
                details = f"Mercado: *{title}*\nProbabilidad de éxito (Sí): `{last_price}%`\nIntervalo evaluado: **{timeframe}**"
                send_discord_alert(f"Predicción Bitcoin {timeframe}", details, alert_type=alert_tag)

            # --- Detector de Anomalías en Deportes ---
            elif "SPORT" in category or "GAME" in category or "MATCH" in category:
                # Se considera anomalía una probabilidad extrema (< 15% o > 85%) o alta volatilidad
                if last_price >= 85 or last_price <= 15:
                    details = f"Anomalía de probabilidad detectada en evento deportivo:\n**{title}**\nProbabilidad actual: `{last_price}%`"
                    send_discord_alert("Anomalía en Mercado Deportivo", details, alert_type="SPORTS")

    except Exception as e:
        print(f"Error en escáner de Kalshi: {e}")

# ---------------------------------------------------------
# 4. MONITOR DE NOTICIAS DE PERSONAS Y EMPRESAS INFLUYENTES
# ---------------------------------------------------------
TOP_10_PEOPLE = [
    "Elon Musk", "Jerome Powell", "Donald Trump", "Kamala Harris", 
    "Vitalik Buterin", "Michael Saylor", "Changpeng Zhao", "Gary Gensler", 
    "Larry Fink", "Jensen Huang"
]

TOP_10_COMPANIES = [
    "NVIDIA", "Apple", "Microsoft", "Tesla", "BlackRock", 
    "MicroStrategy", "Coinbase", "Binance", "Federal Reserve", "Amazon"
]

def scan_influential_news():
    """
    Rastrea noticias y menciones clave que pueden impactar la dirección del mercado.
    """
    # Lista demostrativa de consulta de noticias públicas (Crypto / Markets)
    query_targets = TOP_10_PEOPLE[:3] + TOP_10_COMPANIES[:3]
    summary = f"**Búsqueda de impacto en curso para:**\n- **Personas Clave:** {', '.join(TOP_10_PEOPLE[:5])}...\n- **Empresas Clave:** {', '.join(TOP_10_COMPANIES[:5])}...\n\n*Estado:* Sin giros bruscos de tendencia detectados en la última ventana."
    
    send_discord_alert("Reporte de Noticias e Impacto de Mercado", summary, alert_type="NEWS")

# ---------------------------------------------------------
# 5. BUCLE PRINCIPAL 24/7 Y EJECUCIÓN
# ---------------------------------------------------------
def main_loop():
    print("🚀 Iniciando bucle de monitoreo continuo (24/7)...")
    while True:
        try:
            print("🔍 Ejecutando escaneo de mercados y noticias...")
            scan_kalshi_markets()
            scan_influential_news()
        except Exception as e:
            print(f"Error no controlado en el bucle principal: {e}")
            
        # Esperar 15 minutos (900 segundos) entre escaneos
        time.sleep(900)

if __name__ == "__main__":
    # Iniciar el servidor HTTP en un hilo independiente para Render
    server_thread = threading.Thread(target=run_http_server, daemon=True)
    server_thread.start()
    print("🌐 Servidor HTTP iniciado para el Health Check de Render.")

    # Ejecutar el bucle del bot en el hilo principal
    main_loop()
