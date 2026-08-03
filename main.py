import asyncio
import json
import os
import threading
import requests
import websockets
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# CONFIGURACIÓN GENERAL Y PARÁMETROS
# ==========================================
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL"  # Reemplaza con tu Webhook de Discord

# Parámetros de Trading y Filtros
KALSHI_CONTRACT_MIN_PRICE = 0.30
KALSHI_CONTRACT_MAX_PRICE = 0.35
WHALE_THRESHOLD_BTC = 5.0
ENTRY_WINDOW_START_MIN = 1
ENTRY_WINDOW_END_MIN = 4

# Gestión de Riesgo
INITIAL_BALANCE = 100.0
DAILY_STOP_LOSS = 12.0
TRAILING_STOP_PERCENT = 0.02  # 2% Trailing Stop

# Estado Global del Bot
current_daily_loss = 0.0
active_position = None
volatility_pause = False
price_history = []
candle_15m_closes = []  # Cierres de velas de 15m para evaluar volatilidad

# ==========================================
# SERVIDOR HTTP DUMMY (FIX DEFINITIVO DE RENDER)
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK - Bot activo y funcionando en Render")

    def log_message(self, format, *args):
        # Silenciar logs HTTP rutinarios para no saturar la consola de Render
        return

def run_health_check_server():
    """Servidor web secundario para que Render y UptimeRobot mantengan la app activa 24/7."""
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌐 [Web Service] Servidor Health Check escuchando en el puerto {port}")
    server.serve_forever()

# ==========================================
# SERVICIO DE NOTIFICACIONES DISCORD
# ==========================================
def send_discord_alert(message: str, title: str = "🤖 Bot Alert"):
    """Envía notificaciones formateadas a Discord vía Webhook."""
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "YOUR_DISCORD_WEBHOOK_URL":
        print(f"[{title}] {message}")
        return

    payload = {
        "embeds": [{
            "title": title,
            "description": message,
            "color": 3447003,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        print(f"Error enviando alerta a Discord: {e}")

# ==========================================
# MÓDULO DE NOTICIAS, INFLUENCERS Y PRUEBAS
# ==========================================
def process_news_or_signal(text: str):
    """Procesa noticias o menciones para generar señales alcistas/bajistas."""
    print(f"[Análisis de Noticia/Texto]: {text}")
    text_lower = text.lower()
    
    if any(keyword in text_lower for keyword in ["subir", "alcista", "bullish", "comprar", "pump"]):
        send_discord_alert(
            f"📢 **SEÑAL ALCISTA DETECTADA**\n- **Noticia:** '{text}'\n- **Acción:** COMPRAR ALCISTA (CALL)",
            title="📰 Análisis de Noticias"
        )
    elif any(keyword in text_lower for keyword in ["bajar", "bajista", "bearish", "vender", "dump"]):
        send_discord_alert(
            f"📢 **SEÑAL BAJISTA DETECTADA**\n- **Noticia:** '{text}'\n- **Acción:** COMPRAR BAJISTA (PUT)",
            title="📰 Análisis de Noticias"
        )

# ==========================================
# MÓDULO DE PREDICCIONES DEPORTIVAS
# ==========================================
def check_sports_prediction(matchup: str, prediction_details: str = ""):
    """Módulo para seguimiento de pronósticos deportivos (ej. Tenis)."""
    msg = f"🎾 **Análisis Deportivo:** {matchup}"
    if prediction_details:
        msg += f"\n- **Pronóstico:** {prediction_details}"
    send_discord_alert(msg, title="🏆 Predicción Deportiva")

# ==========================================
# FILTROS Y VOLATILIDAD POR VELAS DE 15 MIN
# ==========================================
def is_within_entry_window() -> bool:
    """Verifica si estamos entre el minuto 1 y 4 de la vela de 15 min."""
    now = datetime.now(timezone.utc)
    minute_in_candle = now.minute % 15
    return ENTRY_WINDOW_START_MIN <= minute_in_candle <= ENTRY_WINDOW_END_MIN

def check_15m_volatility_filter(closes: list) -> bool:
    """
    Evalúa si hay alternancia errática (zig-zag) en los últimos 4 cierres de 15 minutos.
    Ejemplo: Cierre 1 Abajo, Cierre 2 Arriba, Cierre 3 Abajo, Cierre 4 Arriba.
    """
    if len(closes) < 4:
        return False
    
    # Evaluar direcciones de las velas consecutivas
    d1 = closes[1] - closes[0]
    d2 = closes[2] - closes[1]
    d3 = closes[3] - closes[2]

    # Si cambia de dirección continuamente (arriba->abajo->arriba o viceversa)
    is_zigzag = (d1 > 0 and d2 < 0 and d3 > 0) or (d1 < 0 and d2 > 0 and d3 < 0)
    return is_zigzag

# ==========================================
# EJECUCIÓN EN KALSHI & TRAILING STOP
# ==========================================
async def execute_kalshi_trade(direction: str, current_price: float):
    global current_daily_loss, active_position

    if current_daily_loss >= DAILY_STOP_LOSS:
        send_discord_alert("⛔ **Límite de pérdida diaria alcanzado ($12 USD).** Bot pausado.", title="Risk Management")
        return

    estimated_contract_price = 0.32
    if not (KALSHI_CONTRACT_MIN_PRICE <= estimated_contract_price <= KALSHI_CONTRACT_MAX_PRICE):
        send_discord_alert(f"⚠️ Contrato fuera de rango (${estimated_contract_price}). Descartado.", title="Filtro Kalshi")
        return

    active_position = {
        "direction": direction,
        "entry_price": current_price,
        "highest_price": current_price,
        "lowest_price": current_price,
        "contract_price": estimated_contract_price,
        "timestamp": datetime.now(timezone.utc)
    }

    send_discord_alert(
        f"🚀 **Orden Ejecutada en Kalshi**\n"
        f"- **Dirección:** {direction}\n"
        f"- **Precio BTC:** ${current_price:,.2f}\n"
        f"- **Contrato:** ${estimated_contract_price}",
        title="Entrada Kalshi"
    )

def manage_trailing_stop(current_price: float):
    """Aplica Trailing Stop-Loss dinámico."""
    global active_position, current_daily_loss
    if not active_position:
        return

    direction = active_position["direction"]
    entry_price = active_position["entry_price"]

    if direction == "BUY_UP":
        if current_price > active_position["highest_price"]:
            active_position["highest_price"] = current_price
        
        stop_price = active_position["highest_price"] * (1 - TRAILING_STOP_PERCENT)
        if current_price <= stop_price and current_price > entry_price:
            send_discord_alert(f"🎯 **Trailing Stop CERRADO en ganancia.** Precio: ${current_price:,.2f}", title="Cierre de Posición")
            active_position = None
        elif current_price <= entry_price * (1 - TRAILING_STOP_PERCENT):
            loss = active_position["contract_price"] * 10
            current_daily_loss += loss
            send_discord_alert(f"🔻 **Stop-Loss alcanzado.** Pérdida hoy: ${current_daily_loss:.2f}", title="Cierre con Pérdida")
            active_position = None

# ==========================================
# WEBSOCKET COINBASE (DATOS EN TIEMPO REAL)
# ==========================================
async def coinbase_websocket_listener():
    global volatility_pause, candle_15m_closes
    ws_url = "wss://ws-feed.exchange.coinbase.com"

    subscribe_message = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["matches"]
    }

    async for websocket in websockets.connect(ws_url):
        try:
            await websocket.send(json.dumps(subscribe_message))
            send_discord_alert("🟢 **WebSocket de Coinbase conectado.** Monitoring activo.", title="System Status")

            async for message in websocket:
                data = json.loads(message)
                if data.get("type") == "match":
                    price = float(data["price"])
                    size = float(data["size"])
                    side = data["side"]

                    # 1. Alertas de Ballenas (> 5 BTC)
                    if size >= WHALE_THRESHOLD_BTC:
                        send_discord_alert(
                            f"🐋 **Movimiento de Ballena Detectado**\n"
                            f"- **Monto:** {size:.2f} BTC\n"
                            f"- **Tipo:** {side.upper()}\n"
                            f"- **Precio:** ${price:,.2f}",
                            title="Whale Alert"
                        )

                    # 2. Gestión de Trailing Stop
                    manage_trailing_stop(price)

                    # 3. Evaluación de entradas por ventana de tiempo y filtro de volatilidad
                    if is_within_entry_window() and not active_position and not volatility_pause:
                        # Ejecutar entrada si las condiciones están dadas
                        pass

        except websockets.ConnectionClosed:
            send_discord_alert("⚠️ **Conexión perdida con Coinbase. Reconectando...**", title="System Status")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Error en WebSocket: {e}")
            await asyncio.sleep(5)

# ==========================================
# INICIO DEL SISTEMA Y SERVICIOS
# ==========================================
if __name__ == "__main__":
    # 1. Iniciar servidor HTTP en segundo plano para Render y UptimeRobot
    threading.Thread(target=run_health_check_server, daemon=True).start()

    send_discord_alert("🚀 **Bot Unificado Iniciado con Fix de Render & Health Check HTTP**", title="System Status")
    
    # 2. Pruebas iniciales de módulos
    process_news_or_signal("TEST PRUEBA: Noticia alcista detectada para Bitcoin")
    check_sports_prediction("Rafael Jodar vs. Lorenzo Musetti", "Análisis favorable.")

    # 3. Iniciar escucha del WebSocket
    asyncio.run(coinbase_websocket_listener())
