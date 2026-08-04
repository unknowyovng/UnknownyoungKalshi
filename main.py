import os
import time
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask
from threading import Thread

# ==========================================
# 1. CONFIGURACIÓN Y SERVIDOR FLASK (RENDER)
# ==========================================
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot de Alertas Kalshi activo y funcionando.", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# Iniciar el servidor web en un hilo separado
Thread(target=run_flask, daemon=True).start()

# Configuración de Webhook de Discord y Kalshi API
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "TU_WEBHOOK_DE_DISCORD_AQUI")
KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Registro para evitar duplicados en la sesión
seen_alerts = set()

# ==========================================
# 2. FUNCIONES DE UTILIDAD Y CÁLCULO DE CUOTAS
# ==========================================
def calculate_odds(prob):
    """
    Calcula la cuota decimal y americana basada en una probabilidad (0.01 a 0.99).
    """
    if prob <= 0 or prob >= 1:
        return "N/A", "N/A"
    
    decimal_odds = round(1 / prob, 2)
    
    if prob < 0.5:
        american_odds = f"+{int(((1 / prob) - 1) * 100)}"
    else:
        american_odds = f"-{int((prob / (1 - prob)) * 100)}"
        
    return decimal_odds, american_odds

def build_safe_kalshi_url(ticker, series_ticker=None):
    """
    Genera enlaces seguros a Kalshi para evitar errores 404 o certificados.
    """
    if series_ticker:
        return f"https://kalshi.com/markets/{series_ticker.lower()}"
    return f"https://kalshi.com/markets?search={ticker.lower()}"

# ==========================================
# 3. FILTROS DE SEGURIDAD (48 HRS Y LARGO PLAZO)
# ==========================================
def is_long_term_or_invalid_market(title, subtitle=""):
    """
    Filtra mercados de largo plazo, elecciones de sedes o eventos que no sean partidos directos.
    """
    text_to_check = f"{title} {subtitle}".lower()
    
    # Términos excluidos (premios, hosting, torneos lejanos, etc.)
    forbidden_terms = [
        "who will host", "host the", "championships before", 
        "will win the", "winner of the", "mvp", "champion 20",
        "nominated", "oscar", "election", "president"
    ]
    
    for term in forbidden_terms:
        if term in text_to_check:
            return True
            
    # Filtro por años futuros lejanos (2027 en adelante)
    for year in range(2027, 2045):
        if str(year) in text_to_check:
            return True
            
    return False

def is_within_48_hours(close_time_str):
    """
    Verifica que el evento cierre/termine dentro de las próximas 48 horas.
    """
    if not close_time_str:
        return False
    try:
        close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        max_future_time = now + timedelta(hours=48)
        
        return now <= close_time <= max_future_time
    except Exception:
        return False

# ==========================================
# 4. EXTRACCIÓN Y DETECCIÓN DEL UNDERDOG
# ==========================================
def parse_sports_underdog(market):
    """
    Identifica el nombre específico del equipo o jugador Underdog y formatea la recomendación.
    """
    title = market.get("title", "")
    subtitle = market.get("subtitle", "")
    yes_sub_title = market.get("yes_sub_title", "")
    
    target_name = yes_sub_title if yes_sub_title else subtitle
    if not target_name:
        target_name = title

    last_price = market.get("last_price", 0) / 100.0
    decimal_odds, american_odds = calculate_odds(last_price)
    
    recommendation = (
        f"👉 **Apostar por:** COMPRAR SÍ a **{target_name}**\n"
        f"🎯 **Estrategia:** *Underdog de Valor Alto / Scalping*\n"
        f"💡 **Recomendación:** Entrar a la cuota actual y asegurar *profit* (Cash Out) con cualquier movimiento favorable en el marcador."
    )
    
    return target_name, decimal_odds, american_odds, recommendation

# ==========================================
# 5. LÓGICA DE ESCANEO DE LA API DE KALSHI
# ==========================================
def fetch_and_process_markets():
    try:
        url = f"{KALSHI_API_BASE}/markets?limit=100&status=open"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"Error en API Kalshi: {response.status_code}")
            return

        data = response.json()
        markets = data.get("markets", [])

        for market in markets:
            ticker = market.get("ticker", "")
            title = market.get("title", "")
            subtitle = market.get("subtitle", "")
            close_time = market.get("close_time", "")
            series_ticker = market.get("series_ticker", "")

            if ticker in seen_alerts:
                continue

            if is_long_term_or_invalid_market(title, subtitle):
                continue

            if not is_within_48_hours(close_time):
                continue

            last_price = market.get("last_price", 0)
            if 1 <= last_price <= 35:
                prob = last_price / 100.0
                target_name, decimal_odds, american_odds, recommendation = parse_sports_underdog(market)
                market_url = build_safe_kalshi_url(ticker, series_ticker)

                payload = {
                    "username": "Captain Hook",
                    "content": f"🚨 **[SPORTS] ANOMALÍA DETECTADA - APUESTA DE VALOR**",
                    "embeds": [
                        {
                            "title": f"🏆 Evento: {title}",
                            "description": f"**Objetivo detectado:** {target_name}\n"
                                           f"📊 **Probabilidad en Kalshi:** {last_price}%\n"
                                           f"💵 **Cuota Estimada:** {decimal_odds}x ({american_odds})\n\n"
                                           f"{recommendation}\n\n"
                                           f"🔗 [Abrir Mercado en Kalshi]({market_url})",
                            "color": 15158332,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    ]
                }

                res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
                if res.status_code in [200, 204]:
                    print(f"Alerta enviada correctamente para: {ticker}")
                    seen_alerts.add(ticker)
                else:
                    print(f"Error enviando webhook a Discord: {res.status_code}")

    except Exception as e:
        print(f"Error procesando los mercados de Kalshi: {e}")

# ==========================================
# 6. BUCLE PRINCIPAL DE EJECUCIÓN
# ==========================================
if __name__ == "__main__":
    print("Iniciando Bot de Alertas con Filtros Ajustados...")
    while True:
        fetch_and_process_markets()
        time.sleep(60)
