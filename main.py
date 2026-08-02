import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands

# ==========================================
# SERVIDOR WEB FALSO PARA RENDER (GRATIS)
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot activo")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

# Iniciar servidor en hilo secundario
threading.Thread(target=run_dummy_server, daemon=True).start()

# ==========================================
# LÓGICA DE TU BOT
# ==========================================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

manual_target = None
modo_manual = False

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como: {bot.user.name}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.content.startswith("!"):
        print(f"📩 Comando: {message.content}")
    await bot.process_commands(message)

@bot.command(name="target")
async def set_target(ctx, valor: str = None):
    global manual_target, modo_manual
    if valor is None:
        estado = f"🎯 Target: ${manual_target:.2f}" if modo_manual else "🤖 Modo: AUTO"
        await ctx.send(f"ℹ️ {estado}")
        return

    if valor.lower() in ["auto", "reset", "automatico"]:
        modo_manual = False
        manual_target = None
        await ctx.send("🤖 **Target restablecido a MODO AUTOMÁTICO.**")
    else:
        try:
            precio = float(valor.replace(",", "").replace("$", ""))
            manual_target = precio
            modo_manual = True
            await ctx.send(f"🎯 **Target fijado manualmente en:** `${manual_target:.2f}`")
        except ValueError:
            await ctx.send("❌ Error en formato de número.")

async def main():
    async with bot:
        token = os.environ.get("DISCORD_BOT_TOKEN")
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
