import asyncio
import json
import logging
import requests
import websockets

# ==========================================
# CONFIGURACIÓN GENERAL Y APIS
# ==========================================
DISCORD_WEBHOOK_URL = "TU_DISCORD_WEBHOOK_URL_AQUI"

# Configuración Trading / Cripto
COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
WHALE_THRESHOLD_BTC = 5.0  # Detección de ballenas (>5 BTC)

# Configuración Deportes / Pronósticos
ODDS_API_KEY = "TU_ODDS_API_KEY_AQUI"  # Ejemplo: The-Odds-API o similar
SPORTS_TO_TRACK = [
    "tennis_atp",
    "tennis_wta",
    "soccer_epl",
    "basketball_nba",
    "americanfootball_nfl"
]

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ==========================================
# SISTEMA DE NOTIFICACIONES
# ==========================================
def send_discord_alert(content: str, title: str = "🚨 ALERTA DEL BOT"):
    """Envía un mensaje formateado a Discord a través de Webhook."""
    if DISCORD_WEBHOOK_URL == "TU_DISCORD_WEBHOOK_URL_AQUI":
        logging.warning("Discord Webhook no configurado. Mensaje impreso en consola.")
        print(f"\n--- {title} ---\n{content}\n")
        return

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
# MÓDULO 1: MONITOR DE TRADING (COINBASE / KALSHI)
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
                logging.info("Conectado a Coinbase WebSocket (BTC-USD).")

                while True:
                    response = await ws.recv()
                    data = json.loads(response)

                    if data.get("type") == "match":
                        size = float(data.get("size", 0))
                        price = float(data.get("price", 0))
                        side = data.get("side")

                        # Filtro de Volatilidad / Ballenas
                        if size >= WHALE_THRESHOLD_BTC:
                            direction = "🟢 COMPRA (UP)" if side == "buy" else "🔴 VENTA (DOWN)"
                            msg = (
                                f"**Activo:** BTC-USD\n"
                                f"**Dirección:** {direction}\n"
                                f"**Volumen:** `{size:.2f} BTC`\n"
                                f"**Precio:** `${price:,.2f}`\n"
                                f"**Plataforma sugerida:** Kalshi / Coinbase"
                            )
                            send_discord_alert(msg, title="🐋 ALERTA TRADING / BALLENA")

        except (websockets.ConnectionClosed, Exception) as e:
            logging.warning(f"Reconectando servicio de trading por error: {e}")
            await asyncio.sleep(5)

# ==========================================
# MÓDULO 2: MONITOR DE DEPORTES MULTIDISCIPLINA
# ==========================================
async def monitor_sports_signals():
    """Consulta periódicamente datos y cuotas para múltiples disciplinas deportivas."""
    logging.info(f"Módulo de deportes activado para: {', '.join(SPORTS_TO_TRACK)}")
    
    while True:
        try:
            for sport in SPORTS_TO_TRACK:
                # Lógica de escaneo de probabilidades / valor en apuestas
                # Aquí se conecta a la API de deportes elegida
                await process_sport_data(sport)
                
            # Intervalo de revisión (ej. cada 15 minutos)
            await asyncio.sleep(900)
        except Exception as e:
            logging.error(f"Error en módulo de deportes: {e}")
            await asyncio.sleep(60)

async def process_sport_data(sport_key: str):
    """Procesa cuotas y genera alertas de valor por deporte."""
    # Simulación de detección de oportunidad/alerta
    # Reemplazar con llamadas a endpoints específicos según el proveedor de datos
    pass

def send_manual_sports_signal(sport: str, match: str, prediction: str, odds: str):
    """Permite enviar manualmente o desde script un pronóstico deportivo formateado."""
    msg = (
        f"**Deporte:** {sport.upper()}\n"
        f"**Partido/Evento:** {match}\n"
        f"**Pronóstico:** `{prediction}`\n"
        f"**Cuota/Odds:** `{odds}`"
    )
    send_discord_alert(msg, title="⚽🎾🏀 SEÑAL DEPORTIVA")

# ==========================================
# EJECUCIÓN PRINCIPAL (CONCURRENTE)
# ==========================================
async def main():
    logging.info("Iniciando Bot Unificado de Trading y Deportes...")
    
    # Ejecutar ambos módulos de forma simultánea
    await asyncio.gather(
        monitor_coinbase_trading(),
        monitor_sports_signals()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] Bot detenido por el usuario.")
