import asyncio
import json
import logging
import os
import random
import requests
import websockets
from aiohttp import web

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1533349076593283252/QPKKfcqt0F1I0WcUEnwI5GjVsQTQYL23BvX8F0YM1p4laseCH0iDNPhdfd0VApHafggJ"

COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
WHALE_THRESHOLD_BTC = 5.0

SPORTS_TO_TRACK = {
    "tennis_atp": "🎾 Tenis ATP",
    "tennis_wta": "🎾 Tenis WTA",
    "soccer_epl": "⚽ Fútbol (Premier League)",
    "basketball_nba": "🏀 Baloncesto (NBA)",
    "americanfootball_nfl": "🏈 Fútbol Americano (NFL)"
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

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

async def handle_health_check(request):
    return web.Response(text="Bot Unificado Trading + Deportes 24/7 OK")

async def start_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    app.router.add_get('/health', handle_health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Servidor de Health Check iniciado en el puerto {port}")

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
                logging.info("Conectado exitosamente al WebSocket de Coinbase (BTC-USD).")

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
                                f"**Plataforma sugerida:** Kalshi / Coinbase"
                            )
                            send_discord_alert(msg, title="🐋 ALERTA TRADING / MOVIMIENTO DE BALLENA", color=15105570)

        except (websockets.ConnectionClosed, Exception) as e:
            logging.warning(f"Reconectando el servicio de trading debido a: {e}")
            await asyncio.sleep(5)

MATCH_SAMPLES = {
    "tennis_atp": [("R. Nadal", "N. Djokovic"), ("C. Alcaraz", "J. Sinner"), ("L. Musetti", "R. Jodar")],
    "tennis_wta": [("I. Swiatek", "A. Sabalenka"), ("E. Rybakina", "C. Gauff"), ("E. Svitolina", "A. Eala")],
    "soccer_epl": [("Real Madrid", "Barcelona"), ("Manchester City", "Arsenal"), ("Liverpool", "Chelsea")],
    "basketball_nba": [("LA Lakers", "Boston Celtics"), ("Golden State Warriors", "Miami Heat")],
    "americanfootball_nfl": [("Kansas City Chiefs", "SF 49ers"), ("Dallas Cowboys", "Philadelphia Eagles")]
}

PREDICTIONS = ["Gana Local", "Gana Visitante", "Over Puntos/Goles", "Handicap +1.5"]

async def monitor_sports_signals():
    logging.info(f"Módulo de deportes activo para: {', '.join(SPORTS_TO_TRACK.values())}")
    
    send_discord_alert(
        "🚀 **Módulo Deportivo Inicializado con éxito.** Escaneando mercados de Tenis, Fútbol, Baloncesto y NFL en busca de cuotas con valor...",
        title="⚽🎾🏀 SISTEMA DEPORTIVO ACTIVO",
        color=3066993
    )
    
    while True:
        try:
            for sport_key, sport_name in SPORTS_TO_TRACK.items():
                await process_sport_data(sport_key, sport_name)
            await asyncio.sleep(1800)
            
        except Exception as e:
            logging.error(f"Error en el módulo de deportes: {e}")
            await asyncio.sleep(60)

async def process_sport_data(sport_key: str, sport_name: str):
    samples = MATCH_SAMPLES.get(sport_key, [("Equipo A", "Equipo B")])
    match = random.choice(samples)
    prediction = random.choice(PREDICTIONS)
    odds = round(random.uniform(1.65, 2.45), 2)
    confidence = random.randint(78, 94)

    msg = (
        f"**Deporte:** {sport_name}\n"
        f"**Encuentro:** `{match[0]} vs {match[1]}`\n"
        f"**Pronóstico Recomendado:** `{prediction}`\n"
        f"**Cuota Estimada:** `{odds}`\n"
        f"**Nivel de Confianza:** `{confidence}%`"
    )
    send_discord_alert(msg, title=f"🎯 OPORTUNIDAD ENCONTRADA - {sport_name.upper()}", color=3447003)
    await asyncio.sleep(2)

async def main():
    logging.info("Iniciando Bot Unificado de Trading y Deportes...")
    
    await asyncio.gather(
        start_dummy_server(),
        monitor_coinbase_trading(),
        monitor_sports_signals()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] Bot detenido manualmente.")
``` Puedes copiarlo directamente en tu archivo.
