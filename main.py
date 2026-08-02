import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands

# ==========================================
# 1. SERVIDOR WEB FALSO (Render Gratis)
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# ==========================================
# 2. CONFIGURACIÓN DE DISCORD
# ==========================================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

manual_target = None
modo_manual = False

# ==========================================
# 3. COMANDOS (!target)
# ==========================================
@bot.command(name="target")
async def set_target(ctx, valor: str = None):
    global manual_target, modo_manual

    if valor is None:
        estado = f"🎯 Target actual: ${manual_target:.2f}" if modo_manual else "🤖 Modo: AUTOMÁTICO (15m)"
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
            await ctx.send("❌ Formato incorrecto. Ejemplo: `!target 63629.00`")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

# ==========================================
# 4. CICLO DE MONITOREO AUTOMÁTICO
# ==========================================
async def ciclo_monitoreo():
    await bot.wait_until_ready()
    
    # Busca el canal por nombre sin requerir IDs
    canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")

    while not bot.is_closed():
        try:
            if canal:
                # --------------------------------------------------
                # AQUÍ TU LÓGICA DE BTC / CÁLCULOS
                # --------------------------------------------------
                precio_btc = 63468.01
                global manual_target, modo_manual
                target_calculado_auto = 63456.97
                target_activo = manual_target if modo_manual and manual_target else target_calculado_auto

                print(f"🔍 Monitoreando... BTC: {precio_btc} | Target Activo: {target_activo}")
            else:
                print("⚠️ No se encontró el canal 'alertas-kalshi'")

        except Exception as e:
            print(f"⚠️ Error en monitoreo: {e}")

        await asyncio.sleep(15)

# ==========================================
# 5. INICIALIZACIÓN
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como: {bot.user.name}")
    bot.loop.create_task(ciclo_monitoreo())

async def main():
    async with bot:
        token = os.environ.get("DISCORD_BOT_TOKEN")
        if not token:
            raise ValueError("Falta DISCORD_BOT_TOKEN en las variables de entorno.")
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
