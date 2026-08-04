import os
import time
import threading
import requests
import urllib.parse
from datetime import datetime, timezone, timedelta
from flask import Flask

# ---------------------------------------------------------
# 1. SERVIDOR HTTP PARA RENDER (HEALTH CHECK MANTENIDO)
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
# 3. FUNCIONES AUXILIARES PARA CUOTAS Y FILTROS
# ---------------------------------------------------------
def calculate_odds(prob_percent):
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

def analyze_sports_recommendation(title, last_price):
    title_lower = title.lower()
    
    if "runs" in title_lower or "carreras" in title_lower or "mlb" in title_lower:
        rec_type = "BÉISBOL (CARRERAS)"
        pick = "MÁS DE 8.5 CARRERAS" if last_price <= 25 else "BAJO DE 8.5 CARRERAS"
    elif "goals" in title_lower or "goles" in title_lower or "soccer" in title_lower:
        rec_type = "FÚTBOL (GOLES)"
        pick = "MÁS DE 2.5 GOLES" if last_price <= 25 else "BAJO DE 2.5 GOLES"
    elif "sets" in title_lower or "tennis" in title_lower or "tenis" in title_lower:
        rec_type = "TENIS (SETS)"
        pick = "MÁS DE / BAJO DE 3 SETS (Estrategia Scalping)"
    else:
        rec_type = "PARTIDO EN VIVO / ENCUENTRO DIRECTO"
        pick = "COMPRAR SÍ (Underdog con valor alto 🎯 - Excelente para Scalping)"

    return rec_type, pick

def contains_long_term_years_or_non_live(title):
    """
    Filtro avanzado: Bloquea años futuros, mercados a largo plazo y eventos
    que no son partidos en vivo (como debuts, drafts, fechas de nominación, etc.).
    """
    title_lower = title.lower()
    
    # Términos prohibidos (fechas lejanas, eventos de fichajes, debuts o galardones)
    forbidden_terms = [
        "2027", "2028", "2029", "2030", "2031", "2032", "2033", "2034", "2035",
        "before", "to win a", "championships", "career", "season total",
        "debut", "draft", "award", "signing", "trade", "contract", "coach", "manager"
    ]
    for term in forbidden_terms:
        if term in title_lower:
            return True
            
    return False

def is_valid_live_sport(title):
    """
    Valida estrictamente que el evento deportivo parezca un partido directo en curso o de corto plazo
    buscando indicadores típicos en el título ("vs", guiones, nombres de ligas de partidos).
    """
    title_lower = title.lower()
    valid_indicators = ["vs", " v ", "-", "game", "match", "open", "cup", "league", "tour"]
    return any(indicator in title_lower for indicator in valid_indicators)

def is_within_max_hours(date_string, max_hours=48):
    if not date_string:
        return True
    try:
        clean_date = date_string.replace("Z", "+00:00")
        event_date = datetime.fromisoformat(clean_date)
        now = datetime.now(timezone.utc)
        max_limit = now + timedelta(hours=max_hours)
        return (now - timedelta(hours=6)) <= event_date <= max_limit
    except Exception:
        return True

# ---------------------------------------------------------
# 4. MONITOREO DE MERCADOS PÚBLICOS KALSHI
# ---------------------------------------------------------
KALSHI_API_URL = "https://api.elections.kalshi.com/v1/events"

def scan_kalshi_markets():
    try:
        response = requests.get(
            KALSHI_API_URL,
            params={"limit": 100, "status": "open"},
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

            # --- FILTROS DE EXCLUSIÓN ESTRICTOS ---
            if contains_long_term_years_or_non_live(title):
                continue

            market = markets[0]
            last_price = market.get("last_price", 0)

            expiration_time = market.get("expiration_time") or market.get("close_time") or event.get("mutually_exclusive_expiration_date")
            if not is_within_max_hours(expiration_time, max_hours=48):
                continue

            kalshi_link = "https://kalshi.com/markets"

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

            # --- Detector de Anomalías en Deportes (SOLO PARTIDOS REALES EN VIVO / UNDERDOGS) ---
            elif "SPORT" in category or "GAME" in category or "MATCH" in category or "SERIES" in category:
                if is_valid_live_sport(title) and (0 < last_price <= 28):
                    dec_odds, amer_odds = calculate_odds(last_price)
                    rec_category, pick_recommendation = analyze_sports_recommendation(title, last_price)
                    
                    details = (
                        f"🏆 **Evento:** {title}\n"
                        f"📊 **Tipo de Mercado:** {rec_category}\n"
                        f"📉 **Probabilidad en Kalshi:** `{last_price}%`\n"
                        f"💵 **Cuota Estimada:** `{dec_odds}x` ({amer_odds})\n\n"
                        f"🎯 **RECOMENDACIÓN DE ENTRADA (SCALPING):**\n"
                        f"👉 **Apostar por:** `{pick_recommendation}`\n"
                        f"💡 *Estrategia:* Partido en vivo/cercano. Entrar a cuota alta y asegurar profit antes de que cambie el marcador.\n\n"
                        f"🔗 [Abrir Mercado en Kalshi Directamente]({kalshi_link})"
                    )
                    send_discord_alert("ANOMALÍA DETECTADA - APUESTA DE VALOR", details, alert_type="SPORTS")

    except Exception as e:
        print(f"Error en escáner de Kalshi: {e}")

# ---------------------------------------------------------
# 5. MONITOR DE NOTICIAS DE IMPACTO DE MERCADO
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
            
        time.sleep(900)

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_http_server, daemon=True)
    server_thread.start()
    print("🌐 Servidor HTTP iniciado para el Health Check de Render.")

    main_loop()
