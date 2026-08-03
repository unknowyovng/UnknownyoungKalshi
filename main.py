import asyncio
import json
import logging
import os
import random
import requests
import websockets
from aiohttp import web

# ==========================================
# CONFIGURACIÓN GENERAL
# ==========================================
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1533349076593283252/QPKKfcqt0F1I0WcUEnwI5GjVsQTQYL23BvX8F0YM1p4laseCH0iDNPhdfd0VApHafggJ"

# Configuración Trading
COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
WHALE_THRESHOLD_BTC = 5.0

# Configuración Deportes (Incluyendo Béisbol)
SPORTS_TO_TRACK = {
    "tennis_atp": "🎾 Tenis ATP",
    "tennis_wta": "🎾 Tenis WTA",
    "soccer_epl": "⚽ Fútbol (Premier League)",
    "basketball_nba": "🏀 Baloncesto (NBA)",
    "americanfootball_nfl": "🏈 Fútbol Americano (NFL)",
    "baseball_mlb": "⚾ Béisbol (MLB)"
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ==========================================
# SISTEMA DE ALERTAS DISCORD
# ==========================================
def send_discord_alert(content: str, title: str = "🚨 ALERTA DEL BOT", color: int = 3447003):
    payload = {
        "embeds": [{
            "title": title,
            "description": content,
            "color": color
        }]
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code not in [200, 204]:
            logging.error(f"Error enviando a Discord: {response.status_code}")
    except Exception as e:
        logging.error(f"Excepción al conectar con Discord: {e}")

# ==========================================
# SERVIDOR WEB (PARA RENDER)
# ==========================================
async def handle_health_check(request):
    return web.Response(text="Bot Unificado Activo 24/7")

async def start_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    app.router.add_get('/health', handle_health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Servidor de Health Check iniciado en puerto {port}")

# ==========================================
# MÓDULO 1: TRADING (COINBASE)
# ==========================================
async def monitor_coinbase_trading():
    subscribe_message = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["matches"]
    }

    while True:
        try:
            async with websockets.connect(COINBASE_WS_URL) as ws:
                await ws.send(json.dumps(subscribe_message))
                logging.info("Conectado a Coinbase WebSocket.")

                while True:
                    response = await ws.recv()
                    data = json.loads(response)

                    if data.get("type") == "match":
                        size = float(data.get("size", 0))
                        price = float(data.get("price", 0))
                        side = data.get("side")

                        if size >= WHALE_THRESHOLD_BTC:
                            direction = "🟢 COMPRA (UP)" if side == "buy" else "🔴 VENTA (DOWN)"
                            msg = (
                                f"**Activo:** BTC-USD\n"
                                f"**Dirección:** {direction}\n"
                                f"**Volumen:** `{size:.2f} BTC`\n"
                                f"**Precio:** `${price:,.2f}`\n"
                                f"**Plataforma:** Kalshi / Coinbase"
                            )
                            send_discord_alert(msg, title="🐋 ALERTA TRADING / BALLENA", color=15105570)

        except (websockets.ConnectionClosed, Exception) as e:
            logging.warning(f"Error en trading: {e}")
            await asyncio.sleep(5)

# ==========================================
# MÓDULO 2: DEPORTES (SIMULADOR)
# ==========================================
MATCH_SAMPLES = {
    "tennis_atp": [("R. Nadal", "N. Djokovic"), ("C. Alcaraz", "J. Sinner"), ("L. Musetti", "R. Jodar")],
    "tennis_wta": [("I. Swiatek", "A. Sabalenka"), ("E. Rybakina", "C. Gauff"), ("E. Svitolina", "A. Eala")],
    "soccer_epl": [("Manchester City", "Arsenal"), ("Liverpool", "Chelsea"), ("Real Madrid", "Barcelona")],
    "basketball_nba": [("LA Lakers", "Boston Celtics"), ("GS Warriors", "Miami Heat")],
    "americanfootball_nfl": [("Kansas City Chiefs", "SF 49ers"), ("Dallas Cowboys", "Philadelphia Eagles")],
    "baseball_mlb": [("NY Yankees", "LA Dodgers"), ("Boston Red Sox", "Houston Astros")]
}

PREDICTIONS = ["Gana Local", "Gana Visitante", "Over/Under", "Handicap"]

async def monitor_sports_signals():
    logging.info("Módulo de deportes iniciado.")
    
    send_discord_alert(
        "🚀 **Sistema Deportivo Iniciado.** Analizando todas las ligas incluyendo MLB...",
        title="⚽🎾🏀 SISTEMA DEPORTIVO ACTIVO",
        color=3066993
    )
    
    while True:
        try:
            for sport_key, sport_name in SPORTS_TO_TRACK.items():
                await process_sport_data(sport_key, sport_name)
            await asyncio.sleep(1800)
            
        except Exception as e:
            logging.error(f"Error en deportes: {e}")
            await asyncio.sleep(60)

async def process_sport_data(sport_key: str, sport_name: str):
    samples = MATCH_SAMPLES.get(sport_key, [("Equipo A", "Equipo B")])
    match = random.choice(samples)
    prediction = random.choice(PREDICTIONS)
    odds = round(random.uniform(1.70, 2.30), 2)
    confidence = random.randint(80, 95)

    msg = (
        f"**Deporte:** {sport_name}\n"
        f"**Evento:** `{match[0]} vs {match[1]}`\n"
        f"**Pronóstico:** `{prediction}`\n"
        f"**Cuota:** `{odds}`\n"
        f"**Confianza:** `{confidence}%`"
    )
    send_discord_alert(msg, title=f"🎯 SEÑAL - {sport_name.upper()}", color=3447003)
    await asyncio.sleep(3)

# ==========================================
# MAIN
# ==========================================
async def main():
    logging.info("Iniciando Bot Unificado...")
    
    await asyncio.gather(
        start_dummy_server(),
        monitor_coinbase_trading(),
        monitor_sports_signals()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot detenido.")
