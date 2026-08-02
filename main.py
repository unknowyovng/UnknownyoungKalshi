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
ultima_senal_enviada = None  # Evita repetir la misma alerta en cada iteración de 15s

# ==========================================
# 3. COMANDOS DE DISCORD (!target)
# ==========================================
@bot.command(name="target")
async def set_target(ctx, valor: str = None):
    global manual_target, modo_manual, ultima_senal_enviada

    if valor is None:
        estado = f"🎯 Target actual: ${manual_target:.2f}" if modo_manual else "🤖 Modo: AUTOMÁTICO (15m)"
        await ctx.send(f"ℹ️ {estado}\nUsa `!target <precio>` o `!target auto` para cambiarlo.")
        return

    if valor.lower() in ["auto", "reset", "automatico"]:
        modo_manual = False
        manual_target = None
        ultima_senal_enviada = None  # Resetea control de señales
        await ctx.send("🤖 **Target restablecido a MODO AUTOMÁTICO.**")
        print("🔄 Target cambiado a MODO AUTOMÁTICO.")
    else:
        try:
            valor_limpio = valor.replace(",", "").replace("$", "")
            precio = float(valor_limpio)
            
            manual_target = precio
            modo_manual = True
            ultima_senal_enviada = None  # Permite evaluar de inmediato el nuevo target
            
            await ctx.send(f"🎯 **Target fijado manualmente en:** `${manual_target:.2f}`")
            print(f"📌 Target fijado manualmente en: {manual_target}")
        except ValueError:
            await ctx.send("❌ **Error:** Formato incorrecto. Ejemplo: `!target 63629.00`")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

# ==========================================
# 4. FUNCIONES DE PRECIO Y LÓGICA DE TRADING
# ==========================================
def obtener_precio_btc():
    """
    Coloca aquí tu llamada real a la API (Kalshi / Binance / etc.)
    """
    return 63468.01

def obtener_target_auto():
    """
    Coloca aquí tu cálculo automático del Target (15m)
    """
    return 63456.97

# ==========================================
# 5. CICLO DE MONITOREO Y ENVÍO DE SEÑALES
# ==========================================
async def ciclo_monitoreo():
    await bot.wait_until_ready()
    global manual_target, modo_manual, ultima_senal_enviada
    
    # Busca el canal 'alertas-kalshi' automáticamente en tu servidor
    canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")

    while not bot.is_closed():
        try:
            if canal:
                # 1. Obtener precio actual y target
                precio_btc = obtener_precio_btc()
                target_calculado_auto = obtener_target_auto()
                
                target_activo = manual_target if modo_manual and manual_target else target_calculado_auto

                print(f"🔍 Monitoreando... BTC: {precio_btc} | Target Activo: {target_activo}")

                # 2. Evaluar condición de señal
                if precio_btc > target_activo:
                    accion = "COMPRAR UP 🚀"
                    diferencia = precio_btc - target_activo
                    identificador_senal = f"{accion}_{target_activo}"

                    # 3. Enviar a Discord solo si es una nueva señal
                    if ultima_senal_enviada != identificador_senal:
                        embed = discord.Embed(
                            title="🚨 NUEVA SEÑAL KALSHI BTC",
                            color=discord.Color.green()
                        )
                        embed.add_field(name="Acción", value=f"🔥 **{accion}**", inline=False)
                        embed.add_field(name="Precio BTC", value=f"${precio_btc:,.2f}", inline=True)
                        embed.add_field(name="Target a Vencer", value=f"${target_activo:,.2f}", inline=True)
                        embed.add_field(name="Detalle", value=f"⚡ Entrada Temprana (+${diferencia:,.2f} sobre Target)", inline=False)

                        # ¡ENVÍA LA SEÑAL A DISCORD!
                        await canal.send(embed=embed)
                        print(f"📢 Señal enviada a Discord: {accion} | Target: {target_activo}")
                        
                        ultima_senal_enviada = identificador_senal

            else:
                print("⚠️ No se encontró el canal 'alertas-kalshi'")

        except Exception as e:
            print(f"⚠️ Error en ciclo de monitoreo: {e}")

        # Escaneo cada 15 segundos
        await asyncio.sleep(15)

# ==========================================
# 6. INICIALIZACIÓN
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como: {bot.user.name}")
    bot.loop.create_task(ciclo_monitoreo())

async def main():
    async with bot:
        token = os.environ.get("DISCORD_BOT_TOKEN")
        if not token:
            raise ValueError("❌ Falta la variable DISCORD_BOT_TOKEN en Render.")
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
