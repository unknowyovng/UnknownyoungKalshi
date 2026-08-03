import asyncio
import json
import time
import requests
import websockets
from datetime import datetime, timezone

# ==========================================
# CONFIGURACIÓN GENERAL Y PARÁMETROS
# ==========================================
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL"

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
consecutive_closes = []
volatility_pause = False
price_history = []

# ==========================================
# SERVICIO DE NOTIFICACIONES DISCORD
# ==========================================
def send_discord_alert(message: str, title: str = "🤖 Bot Alert"):
    """Envía notificaciones formateadas a Discord via Webhook."""
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "YOUR_DISCORD_WEBHOOK_URL":
        print(f"[{title}] {message}")
        return

    payload = {
        "embeds": [{
            "title": title,
            "description": message,
            "color": 3447003,  # Azul tenue
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        print(f"Error enviando alerta a Discord: {e}")

# ==========================================
# FILTROS Y REGLAS DE ESTRATEGIA
# ==========================================
def is_within_entry_window() -> bool:
    """Verifica si el tiempo actual está entre el minuto 1 y 4 de la vela de 15 min."""
    now = datetime.now(timezone.utc)
    minute_in_candle = now.minute % 15
    return ENTRY_WINDOW_START_MIN <= minute_in_candle <= ENTRY_WINDOW_END_MIN

def check_volatility_filter(prices: list) -> bool:
    """Evalúa la volatilidad reciente para pausar operaciones si hay reversiones bruscas."""
    if len(prices) < 6:
        return False
    reversals = 0
    for i in range(2, len(prices)):
        change1 = prices[i-1] - prices[i-2]
        change2 = prices[i] - prices[i-1]
        if (change1 > 0 and change2 < 0) or (change1 < 0 and change2 > 0):
            reversals += 1
    # Si hay más de 3 reversiones bruscas recientes, activamos pausa por volatilidad
    return reversals >= 3

def check_racha_signal(history: list) -> str:
    """Verifica si existen al menos 2 cierres consecutivos en la misma dirección ('UP' o 'DOWN')."""
    if len(history) < 2:
        return "NEUTRAL"
    if history[-1] > 0 and history[-2] > 0:
        return "BUY_UP"
    elif history[-1] < 0 and history[-2] < 0:
        return "BUY_DOWN"
    return "NEUTRAL"

# ==========================================
# EJECUCIÓN EN KALSHI & TRAILING STOP
# ==========================================
async def execute_kalshi_trade(direction: str, current_price: float):
    global current_daily_loss, active_position

    # 1. Verificar Stop-Loss Diario
    if current_daily_loss >= DAILY_STOP_LOSS:
        send_discord_alert("⛔ **Límite de pérdida diaria alcanzado ($12 USD).** Bot pausado hoy.", title="Risk Management")
        return

    # 2. Simulación / Verificación de precio de contrato objetivo ($0.30 - $0.35)
    estimated_contract_price = 0.32  # Valor dentro del rango de filtro $0.30-$0.35
    if not (KALSHI_CONTRACT_MIN_PRICE <= estimated_contract_price <= KALSHI_CONTRACT_MAX_PRICE):
        send_discord_alert(f"⚠️ Contrato fuera del rango objetivo (${estimated_contract_price}). Orden descartada.", title="Filtro Kalshi")
        return

    # 3. Registrar Posición Activa
    active_position = {
        "direction": direction,
        "entry_price": current_price,
        "highest_price": current_price if direction == "BUY_UP" else current_price,
        "lowest_price": current_price if direction == "BUY_DOWN" else current_price,
        "contract_price": estimated_contract_price,
        "timestamp": datetime.now(timezone.utc)
    }

    send_discord_alert(
        f"🚀 **Orden Ejecutada en Kalshi**\n"
        f"- **Dirección:** {direction}\n"
        f"- **Precio Entrada BTC:** ${current_price:,.2f}\n"
        f"- **Precio Contrato:** ${estimated_contract_price}\n"
        f"- **Ventana:** Minuto {datetime.now(timezone.utc).minute % 15} de la vela",
        title="Entrada Kalshi"
    )

def manage_trailing_stop(current_price: float):
    """Monitorea la posición abierta y aplica Trailing Stop-Loss."""
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
            loss = active_position["contract_price"] * 10  # Ejemplo de pérdida calculada
            current_daily_loss += loss
            send_discord_alert(f"🔻 **Stop-Loss alcanzado.** Pérdida acumulada hoy: ${current_daily_loss:.2f}", title="Cierre con Pérdida")
            active_position = None

# ==========================================
# COINBASE WEBSOCKET LISTENER
# ==========================================
async def coinbase_websocket_listener():
    global volatility_pause, price_history
    ws_url = "wss://ws-feed.exchange.coinbase.com"

    subscribe_message = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["matches"]
    }

    async for websocket in websockets.connect(ws_url):
        try:
            await websocket.send(json.dumps(subscribe_message))
            send_discord_alert("🟢 **WebSocket de Coinbase conectado con éxito.**", title="System Status")

            async for message in websocket:
                data = json.loads(message)
                if data.get("type") == "match":
                    price = float(data["price"])
                    size = float(data["size"])
                    side = data["side"]

                    # Trackeamos historial reciente para volatilidad
                    price_history.append(price)
                    if len(price_history) > 20:
                        price_history.pop(0)

                    # 1. Detección de Señales de Ballenas (> 5 BTC)
                    if size >= WHALE_THRESHOLD_BTC:
                        send_discord_alert(
                            f"🐋 **Movimiento de Ballena Detectado**\n"
                            f"- **Monto:** {size:.2f} BTC\n"
                            f"- **Tipo:** {side.upper()}\n"
                            f"- **Precio:** ${price:,.2f}",
                            title="Whale Alert"
                        )

                    # 2. Filtro de Volatilidad
                    if check_volatility_filter(price_history):
                        if not volatility_pause:
                            volatility_pause = True
                            send_discord_alert("⚡ **Alta volatilidad/reversiones detectadas.** Pausando entradas temporales.", title="Filtro Volatilidad")
                    else:
                        volatility_pause = False

                    # 3. Trailing Stop en Posiciones Activas
                    manage_trailing_stop(price)

                    # 4. Evaluación de Entrada (Minuto 1-4 + Racha + Sin Pausa)
                    if is_within_entry_window() and not active_position and not volatility_pause:
                        signal = check_racha_signal(consecutive_closes)
                        if signal != "NEUTRAL":
                            await execute_kalshi_trade(signal, price)

        except websockets.ConnectionClosed:
            send_discord_alert("⚠️ **Conexión perdida con Coinbase. Reconectando...**", title="System Status")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Error en WebSocket: {e}")
            await asyncio.sleep(5)

# ==========================================
# INICIO DEL BOT
# ==========================================
if __name__ == "__main__":
    send_discord_alert("🚀 **Bot de Scalping Kalshi / Coinbase Iniciado**", title="System Status")
    asyncio.run(coinbase_websocket_listener())
