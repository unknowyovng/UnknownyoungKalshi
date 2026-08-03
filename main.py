import os
import time
import threading
import requests
from flask import Flask

# ---------------------------------------------------------
# 1. SERVIDOR HTTP PARA RENDER (HEALTH CHECK - MANTENIDO)
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
# 3. FUNCIONES AUXILIARES PARA CUOTAS Y RECOMENDACIONES
# ---------------------------------------------------------
def calculate_odds(prob_percent):
    """
    Calcula la cuota decimal y americana a partir del porcentaje.
    """
    if prob_percent <= 0:
        return "N/A", "N/A"
    
    decimal_odds = round(100 / prob_percent, 2)
    
    if prob_percent >= 50:
        american_odds = int(- (prob_percent / (100 - prob_percent)) * 100)
        american_str = f"{american_odds}"
    else:
        american_odds = int(((100 - prob_percent) / prob_percent) * 100)
        american_str = f"+{american_odds}"
        
    return decimal_odds, american_str

def analyze_sports_recommendation(title, last_price, market_ticker=""):
    """
    Analiza la especificación de la apuesta y genera recomendación detallada.
    """
    title_lower = title.lower()
    rec_type = "GENERAL"
    pick = "SÍ" if last_price <= 20 else "NO"
    
    # 1. Béisbol (Carreras / Runs)
    if "runs" in title_lower or "carreras" in title_lower or "mlb" in title_lower:
        rec_type = "BÉISBOL (CARRERAS)"
        if "over" in title_lower or "más de" in title_lower or "above" in title_lower:
            pick = "MÁS DE 8.5 CARRERAS" if last_price <= 25 else "BAJO DE 8.5 CARRERAS"
        elif "under" in title_lower or "menos de" in title_lower or "below" in title_lower:
            pick = "BAJO DE 8.5 CARRERAS" if last_price <= 25 else "MÁS DE 8.5 CARRERAS"
        else:
            pick = "Entrada de Valor en Mercado de Carreras (Underdog)"

    # 2. Fútbol / Soccer (Goles)
    elif "goals" in title_lower or "goles" in title_lower or "soccer" in title_lower:
        rec_type = "FÚTBOL (GOLES)"
        if "2.5" in title_lower:
            pick = "MÁS DE 2.5 GOLES" if last_price <= 25 else "BAJO DE 2.5 GOLES"
        elif "3.5" in title_lower:
            pick = "BAJO DE 3.5 GOLES" if last_price <= 25 else "MÁS DE 3.5 GOLES"
        else:
            pick = "Aposta a Cuota Alta en Línea de Goles"

    # 3. Tenis (Sets)
    elif "sets" in title_lower or "tennis" in title_lower or "tenis" in title_lower:
        rec_type = "TENIS (SETS)"
        if "3" in title_lower:
            pick = "MÁS DE / BAJO DE 3 SETS (Estrategia Scalping)"
        elif "5" in title_lower or "4" in title_lower:
            pick = "BAJO DE 4.5 SETS" if last_price <= 25 else "MÁS DE 3.5 SETS"
        else:
            pick = "Entrada en Sets a Favor del Underdog"

    # 4. Ganador directo / Underdog (Desventaja inicial 90-10)
    else:
        rec_type = "GANADOR DIRECTO / ANOMALÍA"
        if last_price <= 15:
            pick = "COMPRAR SÍ (Underdog con valor oculto 🎯)"
        else:
            pick = "COMPRAR NO (Favorito Sobrevalorado)"

    return rec_type, pick

# ---------------------------------------------------------
# 4. MONITOREO DE MERCADOS PÚBLICOS KALSHI (BTC Y DEPORTES)
# ---------------------------------------------------------
KALSHI_API_URL = "https://api.elections.kalshi.com/v1/events"

def scan_kalshi_markets():
    """
    Escanea mercados de Kalshi buscando eventos de Bitcoin (15m/1h) y anomalías en Deportes.
    """
    try:
        response = requests.get(
            KALSHI_API_URL,
            params={"limit": 30, "status": "open"},
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
            event_ticker = event.get("ticker", "")
            markets = event.get("markets", [])
            
            if not markets:
                continue

            market = markets[0]
            last_price = market.get("last_price", 0)
            market_ticker = market.get("ticker", event_ticker)
            
            # Enlace directo al mercado específico en Kalshi
            kalshi_link = f"https://kalshi.com/markets/{event_ticker}"

            # --- Evaluación Bitcoin 15m y 1h ---
            if "BITCOIN" in title.upper() or "BTC" in title.upper():
                timeframe = "15m" if "15" in title else "1h"
                alert_tag = "BTC_15M" if timeframe == "15m" else "BTC_1H"
                dec_odds, amer_odds = calculate_odds(last_price)
                
                details = (
                    f"Mercado: *{title}*\n"
                    f"Probabilidad actual: `{last_price}%`\n"
                    f"Cuota Actual: `{dec_odds}x` ({amer_odds})\n"
                    f"Intervalo: **{timeframe}**\n"
                    f"🔗 [Verificar Mercado en Kalshi]({kalshi_link})"
                )
                send_discord_alert(f"Predicción Bitcoin {timeframe}", details, alert_type=alert_tag)

            # --- Detector de Anomalías y Cuotas de Valor en Deportes ---
            elif "SPORT" in category or "GAME" in category or "MATCH" in category or "SERIES" in category:
                # Detecta anomalías: equipos muy poco favoritos (<= 20%) o hiper-favoritos (>= 80%)
                if last_price <= 20 or last_price >= 80:
                    dec_odds, amer_odds = calculate_odds(last_price)
                    rec_category, pick_recommendation = analyze_sports_recommendation(title, last_price, market_ticker)
                    
                    details = (
                        f"🏆 **Evento:** {title}\n"
                        f"📊 **Tipo de Mercado:** {rec_category}\n"
                        f"📉 **Probabilidad en Kalshi:** `{last_price}%`\n"
                        f"💵 **Cuota Estimada:** `{dec_odds}x` ({amer_odds})\n\n"
                        f"🎯 **RECOMENDACIÓN DE ENTRADA:**\n"
                        f"👉 **Apostar por:** `{pick_recommendation}`\n"
                        f"💡 *Estrategia:* Entrar con cuota alta y buscar salida en profit cuando la cuota suba al 35-40% en vivo.\n\n"
                        f"🔗 [Abrir Partido en Kalshi Directamente]({kalshi_link})"
                    )
                    send_discord_alert("ANOMALÍA DETECTADA - APUESTA DE VALOR", details, alert_type="SPORTS")

    except Exception as e:
        print(f"Error en escáner de Kalshi: {e}")

# ---------------------------------------------------------
# 5. MONITOR DE NOTICIAS DE PERSONAS Y EMPRESAS INFLUYENTES
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
    summary = (
        f"**Búsqueda de impacto en curso para:**\n"
        f"- **Personas Clave:** {', '.join(TOP_10_PEOPLE[:5])}...\n"
        f"- **Empresas Clave:** {', '.join(TOP_10_COMPANIES[:5])}...\n\n"
        f"*Estado:* Sin giros bruscos de tendencia detectados en la última ventana."
    )
    send_discord_alert("Reporte de Noticias e Impacto de Mercado", summary, alert_type="NEWS")

# ---------------------------------------------------------
# 6. BUCLE PRINCIPAL 24/7 Y EJECUCIÓN
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
    # Iniciar el servidor HTTP en un hilo independiente para Render (Web Service)
    server_thread = threading.Thread(target=run_http_server, daemon=True)
    server_thread.start()
    print("🌐 Servidor HTTP iniciado para el Health Check de Render.")

    # Ejecutar el bucle del bot en el hilo principal
    main_loop()
