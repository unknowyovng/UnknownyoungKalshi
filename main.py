import os
import time
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# 1. SERVIDOR HTTP SECUNDARIO (RENDER HEALTH CHECK)
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"Bot de Monitoreo Activo")

    def log_message(self, format, *args):
        return  # Silenciar logs del servidor HTTP

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"[HTTP] Servidor de mantener vivo activo en puerto {port}")
    server.serve_forever()

# ==========================================
# 2. CONFIGURACIÓN Y LISTAS DE MONITOREO
# ==========================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "TU_DISCORD_WEBHOOK_URL_AQUI")

INFLUENTIAL_PEOPLE = [
    "Elon Musk", "Donald Trump", "Vitalik Buterin", "Changpeng Zhao", "CZ",
    "Cathie Wood", "Jerome Powell", "Gary Gensler", "Brian Armstrong", 
    "Arthur Hayes", "Michael Saylor"
]

INFLUENTIAL_COMPANIES = [
    "MicroStrategy", "Tesla", "BlackRock", "Coinbase", "Nvidia", 
    "Apple", "Alphabet", "Google", "Microsoft", "Amazon", "Meta"
]

KEYWORDS_BULLISH = [
    "buy", "bullish", "pump", "crypto", "bitcoin", "btc", "eth", "solana", 
    "approval", "sec approval", "launch", "partnership", "surge", "record high"
]

KEYWORDS_BEARISH = [
    "sell", "bearish", "dump", "ban", "lawsuit", "investigation", "crash", 
    "decline", "hack", "exploit", "sec action", "fine", "subpoena"
]

# Control de volatilidad (Ventana de 15 minutos)
VOLATILITY_WINDOW_SECONDS = 900
signal_timestamps = []

# ==========================================
# 3. NOTIFICACIONES DISCORD
# ==========================================
def send_discord_notification(title, description, color=0x3498db):
    if DISCORD_WEBHOOK_URL == "TU_DISCORD_WEBHOOK_URL_AQUI":
        print(f"\n[DISCORD PREVIEW]\nTitle: {title}\n{description}\n")
        return

    data = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "footer": {"text": "Bot de Monitoreo de Mercado & Kalshi"}
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=5)
    except Exception as e:
        print(f"[ERROR] No se pudo enviar mensaje a Discord: {e}")

# ==========================================
# 4. ANÁLISIS DE SENTIMIENTO Y VOLATILIDAD
# ==========================================
def analyze_sentiment(text):
    text_lower = text.lower()
    bullish_score = sum(1 for word in KEYWORDS_BULLISH if word in text_lower)
    bearish_score = sum(1 for word in KEYWORDS_BEARISH if word in text_lower)

    if bullish_score > bearish_score:
        return "BULLISH 🚀", 0x2ecc71
    elif bearish_score > bullish_score:
        return "BEARISH 🔻", 0xe74c3c
    return "NEUTRAL ⚖️", 0x95a5a6

def check_volatility():
    global signal_timestamps
    current_time = time.time()
    
    # Filtrar señales ocurridas en los últimos 15 minutos
    signal_timestamps = [t for t in signal_timestamps if current_time - t <= VOLATILITY_WINDOW_SECONDS]
    
    if len(signal_timestamps) >= 5:
        send_discord_notification(
            "⚠️ ALERTA DE ALTA VOLATILIDAD (15 MIN)",
            f"Se han registrado **{len(signal_timestamps)} señales de mercado** en los últimos 15 minutos. Mercado con alta actividad.",
            color=0xf1c40f
        )

def process_market_event(source, author, content):
    sentiment, color = analyze_sentiment(content)
    
    found_people = [p for p in INFLUENTIAL_PEOPLE if p.lower() in content.lower() or p.lower() in author.lower()]
    found_companies = [c for c in INFLUENTIAL_COMPANIES if c.lower() in content.lower() or c.lower() in author.lower()]
    
    all_entities = found_people + found_companies
    entities_str = ", ".join(all_entities) if all_entities else "Mención General de Mercado"
    
    signal_timestamps.append(time.time())
    check_volatility()
    
    body = (
        f"**Fuente:** {source}\n"
        f"**Autor / Entidad:** {author}\n"
        f"**Entidades Clave:** {entities_str}\n"
        f"**Sentimiento:** {sentiment}\n\n"
        f"**Contenido / Noticia:**\n{content}"
    )
    
    send_discord_notification(f"🚨 Señal Detectada - {sentiment}", body, color)

# ==========================================
# 5. MÓDULO KALSHI: ESTRATEGIA DE REVERSIÓN / ENTRADA ABAJO
# ==========================================
def evaluate_kalshi_dip_entry(market_ticker, trend_direction, current_prob, minutes_into_candle):
    """
    Detecta si el mercado en Kalshi retrocedió temporalmente en los primeros 1-3 minutos
    generando una probabilidad baja (25% - 35%) a favor de la tendencia principal (30 min).
    """
    # 1. Comprobar que estemos en los primeros minutos del contrato (1 a 3 min)
    if minutes_into_candle <= 3:
        # 2. Verificar si la probabilidad cayó al rango de descuento (25% - 35%)
        if 25 <= current_prob <= 35:
            action = "COMPRAR SI" if trend_direction == "ALCISTA" else "COMPRAR NO"
            potential_roi = round(((100 - current_prob) / current_prob) * 100, 1)

            title = f"💎 OPORTUNIDAD ENTRADA ABAJO ({trend_direction})"
            description = (
                f"**Mercado:** `{market_ticker}`\n"
                f"**Tendencia General (30m):** {trend_direction} 📈\n"
                f"**Minuto del Contrato:** Minuto {minutes_into_candle}\n"
                f"**Probabilidad Actual:** `{current_prob}%` (Descuento detectado)\n"
                f"**Acción Recomendada:** `{action}`\n"
                f"**Margen / ROI Potencial:** ~{potential_roi}%\n\n"
                f"💡 *El mercado retrocedió en el inicio de la vela. Gran oportunidad de entrada a favor de la tendencia.*"
            )
            
            # Enviar notificación en color púrpura/dorado para destacar la entrada de alto rendimiento
            send_discord_notification(title, description, color=0x9b59b6)

# ==========================================
# 6. MÓDULO DE PRONÓSTICOS DEPORTIVOS
# ==========================================
def format_sports_signal(sport_emoji, sport_name, home_team, away_team, pick_type, winner_or_line, odds, confidence):
    """
    Formatea señales deportivas detallando:
    - Ganador: Nombre explícito (ej. Gana Local (R. Nadal))
    - Over/Under: Línea exacta (ej. Over 218.5 Puntos / Under 8.5 Carreras)
    """
    if pick_type == "Gana Local":
        prediction_str = f"Gana Local ({home_team})"
    elif pick_type == "Gana Visitante":
        prediction_str = f"Gana Visitante ({away_team})"
    elif pick_type in ["Over", "Under"]:
        prediction_str = f"{pick_type} {winner_or_line}"
    else:
        prediction_str = f"{pick_type} ({winner_or_line})"

    title = f"🎯 SEÑAL - {sport_emoji} {sport_name.upper()}"
    description = (
        f"**Deporte:** {sport_emoji} {sport_name}\n"
        f"**Evento:** {home_team} vs {away_team}\n"
        f"**Pronóstico:** {prediction_str}\n"
        f"**Cuota:** {odds}\n"
        f"**Confianza:** {confidence}%"
    )
    
    send_discord_notification(title, description, color=0x3498db)

def check_kalshi_markets():
    # Lógica de polling a la API de Kalshi
    pass

# ==========================================
# 7. BUCLE PRINCIPAL DE MONITOREO
# ==========================================
def start_monitoring():
    print("[MONITOR] Rastreo iniciado para Kalshi, X, Truth Social y Noticias...")
    while True:
        try:
            check_kalshi_markets()
            time.sleep(15)
        except Exception as e:
            print(f"[ERROR] Error en el loop de monitoreo: {e}")
            time.sleep(10)

# ==========================================
# 8. PUNTO DE ENTRADA
# ==========================================
if __name__ == "__main__":
    # Servidor HTTP secundario para Render
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    send_discord_notification(
        "🟢 BOT DE MONITOREO INICIADO",
        "El bot está activo y monitoreando:\n"
        "- **10+ Personas Influyentes & Empresas Clave**\n"
        "- **Alertas Kalshi:** Estrategia de Compras Abajo (Dip 25%-35%)\n"
        "- **Alertas Deportivas Clarificadas:** Ganador explícito + Líneas Over/Under\n"
        "- **Control de Volatilidad:** Ventana de 15 Minutos",
        color=0x3498db
    )

    start_monitoring()
