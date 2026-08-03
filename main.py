import asyncio
import json
import logging
import requests
import websockets

# ==========================================
# CONFIGURACIÓN GENERAL Y APIS
# ==========================================
# Discord Webhook integrado
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1533349076593283252/QPKKfcqt0F1I0WcUEnwI5GjVsQTQYL23BvX8F0YM1p4laseCH0iDNPhdfd0VApHafggJ"

# Configuración Trading / Cripto (Coinbase & Kalshi)
COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
WHALE_THRESHOLD_BTC = 5.0  # Detección de movimientos masivos / ballenas (>5 BTC)

# Configuración Deportes Multidisciplina
SPORTS_TO_TRACK = [
    "tennis_atp",
    "tennis_wta",
    "soccer_epl",
    "basketball_nba",
    "americanfootball_nfl"
]

# Configuración de registros / logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ==========================================
# MÓDULO DE NOTIFICACIONES A DISCORD
# ==========================================
def send_discord_alert(content: str, title: str = "🚨 ALERTA DEL BOT"):
    """Envía un mensaje formateado a tu canal de Discord."""
    payload = {
        "embeds": [{
            "title": title,
            "description": content,
            "color": 3447003
        }]
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code not in [200, 204]:
            logging.error(f"Error enviando a Discord: {response.status_code}")
    except Exception as e:
        logging.error(f"Excepción al conectar con Discord: {e}")

# ==========================================
# MÓDULO 1: MONITOR DE TRADING (COINBASE & KALSHI)
# ==========================================
async def monitor_coinbase_trading():
    """Conecta al WebSocket de Coinbase para detectar señales de mercado y ballenas."""
    subscribe_message = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["matches"]
    }

    while True:
        try:
            async with websockets.connect(COINBASE_WS_URL) as ws:
                await ws.send(json.dumps(subscribe_message))
                logging.info("Conectado exitosamente al WebSocket de Coinbase (BTC-USD).")

                while True:
                    response = await ws.recv()
                    data = json.loads(response)

                    if data.get("type") == "match":
                        size = float(data.get("size", 0))
                        price = float(data.get("price", 0))
                        side = data.get("side")

                        # Filtro de Volatilidad y Detección de Ballenas
                        if size >= WHALE_THRESHOLD_BTC:
                            direction = "🟢 COMPRA (UP)" if side == "buy" else "🔴 VENTA (DOWN)"
                            msg = (
                                f"**Activo:** BTC-USD\n"
                                f"**Dirección:** {direction}\n"
                                f"**Volumen:** `{size:.2f} BTC`\n"
                                f"**Precio:** `${price:,.2f}`\n"
                                f"**Plataforma sugerida:** Kalshi / Coinbase"
                            )
                            send_discord_alert(msg, title="🐋 ALERTA TRADING / MOVIMIENTO DE BALLENA")

        except (websockets.ConnectionClosed, Exception) as e:
            logging.warning(f"Reconectando el servicio de trading debido a: {e}")
            await asyncio.sleep(5)

# ==========================================
# MÓDULO 2: MONITOR DE DEPORTES MULTIDISCIPLINA
# ==========================================
async def monitor_sports_signals():
    """Módulo para rastrear y generar señales automáticas en deportes."""
    logging.info(f"Módulo de deportes activo para las disciplinas: {', '.join(SPORTS_TO_TRACK)}")
    
    while True:
        try:
            for sport in SPORTS_TO_TRACK:
                await process_sport_data(sport)
                
            # Intervalo de actualización (por defecto 15 minutos / 900 segundos)
            await asyncio.sleep(900)
        except Exception as e:
            logging.error(f"Error en el módulo de deportes: {e}")
            await asyncio.sleep(60)

async def process_sport_data(sport_key: str):
    """Procesa datos y cuotas para el deporte especificado."""
    # Aquí puedes añadir las llamadas API específicas para consultar eventos deportivos
    pass

def send_manual_sports_signal(sport: str, match: str, prediction: str, odds: str):
    """Permite enviar una señal deportiva específica a Discord."""
    msg = (
        f"**Deporte:** {sport.upper()}\n"
        f"**Partido/Evento:** {match}\n"
        f"**Pronóstico:** `{prediction}`\n"
        f"**Cuota/Odds:** `{odds}`"
    )
    send_discord_alert(msg, title="⚽🎾🏀 SEÑAL DEPORTIVA")

# ==========================================
# EJECUCIÓN PRINCIPAL
# ==========================================
async def main():
    logging.info("Iniciando Bot Unificado de Trading y Deportes...")
    
    # Ejecución simultánea de ambos módulos
    await asyncio.gather(
        monitor_coinbase_trading(),
        monitor_sports_signals()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] Bot detenido manualmente.")
