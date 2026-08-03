import os
import time
import requests
import discord
from discord.ext import tasks, commands

# ---------------------------------------------------------
# CONFIGURACIÓN DE DISCORD
# ---------------------------------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------------
# FUNCIÓN PARA OBTENER DATOS PÚBLICOS DE KALSHI
# ---------------------------------------------------------
KALSHI_PUBLIC_URL = "https://api.elections.kalshi.com/v1/events"

def get_kalshi_markets():
    """
    Obtiene eventos y mercados públicos de Kalshi sin requerir API Key.
    """
    try:
        # Petición a la API pública de Kalshi
        response = requests.get(
            KALSHI_PUBLIC_URL,
            params={"limit": 10, "status": "open"},
            headers={"Accept": "application/json"},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            events = data.get("events", [])
            results = []
            
            for event in events:
                title = event.get("title", "Sin título")
                category = event.get("category", "General")
                markets = event.get("markets", [])
                
                # Tomamos la probabilidad del primer mercado del evento
                prob = "N/A"
                if markets:
                    yes_price = markets[0].get("last_price", 0)
                    prob = f"{yes_price}%"
                
                results.append(f"**[{category}]** {title} ➔ *Probabilidad Si:* `{prob}`")
            
            return results
        else:
            print(f"Error Kalshi HTTP {response.status_code}")
            return []
    except Exception as e:
        print(f"Error consultando Kalshi: {e}")
        return []

# ---------------------------------------------------------
# TAREA PERIÓDICA EN DISCORD (CADA 15 MINUTOS)
# ---------------------------------------------------------
@tasks.loop(minutes=15)
async def send_market_updates():
    if CHANNEL_ID == 0:
        print("ADVERTENCIA: DISCORD_CHANNEL_ID no está configurado.")
        return

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(CHANNEL_ID)
        except Exception as e:
            print(f"No se pudo obtener el canal de Discord: {e}")
            return

    updates = get_kalshi_markets()
    if updates:
        message = "📊 **Actualización de Mercados Kalshi (Público):**\n\n" + "\n".join(updates[:5])
        await channel.send(message)
    else:
        print("No se encontraron actualizaciones o hubo un error al obtener datos.")

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    if not send_market_updates.is_running():
        send_market_updates.start()

# ---------------------------------------------------------
# INICIO DEL BOT
# ---------------------------------------------------------
if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("ERROR: Falta la variable DISCORD_TOKEN en el entorno.")
