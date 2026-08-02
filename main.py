import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands

# ==========================================
# 1. SERVIDOR WEB FALSO (Para Render Free)
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
intents.message_content = True  # Obligatorio para leer comandos

bot = commands.Bot(command_prefix="!", intents=intents)

# Variables globales para el Target
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
# 4. TAREA DE ANÁLISIS Y ENVIÓ DE SEÑALES
# ==========================================
async def ciclo_monitoreo():
    await bot.wait_until_ready()
    # Poner aquí el ID de tu canal de Discord (ej: 123456789012345678)
    canal_id = INT_DE_TU_CANAL  
    canal = bot.get_channel(canal_id)

    while not bot.is_closed():
        try:
            # -----------------------------------------------------------
            # ⚠️ AQUÍ PONES TU LÓGICA DE BTC Y SEÑALES
            # -----------------------------------------------------------
            # 1. Obtener precio actual de BTC de tu API (Binance, Kalshi, etc.)
            precio_btc = 63468.01  # Sustituye por tu llamada a la API
            
            # 2. Determinar el target a usar
            global manual_target, modo_manual
            target_calculado_auto = 63456.97  # Sustituye por tu cálculo auto
            
            target_activo = manual_target if modo_manual and manual_target else target_calculado_auto

            # 3. Evaluar si se envía señal (ejemplo de condición):
            # si cumple las condiciones de tu estrategia:
            # await canal.send(f"🚨 **SEÑAL KALSHI BTC 15M**\nAcción: COMPRAR UP\nTarget: ${target_activo}")

            print(f"🔍 Monitoreando... BTC: {precio_btc} | Target Activo: {target_activo}")

        except Exception as e:
            print(f"⚠️ Error en monitoreo: {e}")

        # Frecuencia de escaneo (ejemplo: revisa cada 15 segundos)
        await asyncio.sleep(15)

# ==========================================
# 5. INICIALIZACIÓN
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como: {bot.user.name}")
    # Arrancar la tarea en segundo plano cuando el bot inicie
    bot.loop.create_task(ciclo_monitoreo())

async def main():
    async with bot:
        token = os.environ.get("DISCORD_BOT_TOKEN")
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
