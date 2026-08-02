import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands

# ==========================================
# 0. SERVIDOR WEB PARA SATISFACER A RENDER
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

# Iniciar servidor web en un hilo secundario
threading.Thread(target=run_dummy_server, daemon=True).start()

# ==========================================
# 1. CONFIGURACIÓN DE INTENTS DE DISCORD
# ==========================================
intents = discord.Intents.default()
intents.message_content = True  # Obligatorio para leer comandos como !target

bot = commands.Bot(command_prefix="!", intents=intents)

manual_target = None
modo_manual = False

# ==========================================
# 2. EVENTOS DEL BOT
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado exitosamente como: {bot.user.name}")
    print("🤖 Esperando comandos en el chat...")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.content.startswith("!"):
        print(f"📩 Comando detectado de {message.author}: {message.content}")

    await bot.process_commands(message)

# ==========================================
# 3. COMANDOS DE DISCORD
# ==========================================
@bot.command(name="target")
async def set_target(ctx, valor: str = None):
    global manual_target, modo_manual

    if valor is None:
        estado = f"🎯 Target actual: ${manual_target:.2f}" if modo_manual else "🤖 Modo: AUTOMÁTICO (15m)"
        await ctx.send(f"ℹ️ {estado}\nUsa `!target <precio>` o `!target auto` para cambiarlo.")
        return

    if valor.lower() in ["auto", "reset", "automatico"]:
        modo_manual = False
        manual_target = None
        await ctx.send("🤖 **Target restablecido a MODO AUTOMÁTICO (15m).**")
        print("🔄 Target cambiado a MODO AUTOMÁTICO.")
    else:
        try:
            valor_limpio = valor.replace(",", "").replace("$", "")
            precio = float(valor_limpio)
            
            manual_target = precio
            modo_manual = True
            
            await ctx.send(f"🎯 **Target fijado manualmente en:** `${manual_target:.2f}`")
            print(f"📌 Target fijado manualmente en: {manual_target}")
        except ValueError:
            await ctx.send("❌ **Error:** Formato incorrecto. Ejemplo: `!target 63629.00`")

# ==========================================
# 4. INICIALIZACIÓN
# ==========================================
async def main():
    async with bot:
        token = os.environ.get("DISCORD_BOT_TOKEN")
        if not token:
            raise ValueError("❌ Falta la variable DISCORD_BOT_TOKEN en Render.")
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
