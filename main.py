import os
import asyncio
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import aiohttp
import discord
from discord.ext import commands

# ==========================================
# 1. SERVIDOR WEB FALSO (Render)
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return

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
target_kalshi_auto = None
ultimo_intervalo_15m = None
ultima_senal_enviada = None

UMBRAL_BALLENA_BTC = 5.0  
MARGEN_MINIMO_CONFIRMACION = 5.0  # Requiere $5 por encima para evitar falsas señales

# ==========================================
# 3. COMANDOS DE DISCORD (!target)
# ==========================================
@bot.command(name="target")
async def set_target(ctx, valor: str = None):
    global manual_target, modo_manual, ultima_senal_enviada

    if valor is None:
        estado = f"🎯 Target actual: ${manual_target:.2f}" if modo_manual else f"🤖 Target Kalshi Auto: ${target_kalshi_auto:.2f}"
        await ctx.send(f"ℹ️ {estado}\nUsa `!target <precio>` o `!target auto` para cambiarlo.")
        return

    if valor.lower() in ["auto", "reset", "automatico"]:
        modo_manual = False
        manual_target = None
        ultima_senal_enviada = None
        await ctx.send("🤖 **Target restablecido a MODO AUTOMÁTICO (Réplica Kalshi 15m).**")
        print("🔄 Target cambiado a MODO AUTOMÁTICO.")
    else:
        try:
            valor_limpio = valor.replace(",", "").replace("$", "")
            precio = float(valor_limpio)
            
            manual_target = precio
            modo_manual = True
            ultima_senal_enviada = None
            
            await ctx.send(f"🎯 **Target fijado manualmente en:** `${manual_target:.2f}`")
            print(f"📌 Target fijado manualmente en: {manual_target}")
        except ValueError:
            await ctx.send("❌ **Error:** Formato incorrecto. Ejemplo: `!target 63469.33`")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

# ==========================================
# 4. CONSULTAS DE PRECIO
# ==========================================
async def obtener_precio_btc(session):
    """Obtiene el precio spot en tiempo real de Bitcoin en Coinbase"""
    url = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
    try:
        async with session.get(url, timeout=3) as resp:
            if resp.status == 200:
                data = await resp.json()
                return float(data["data"]["amount"])
    except Exception:
        pass
    return None

async def buscar_ballenas_binance(session):
    url = "https://api.binance.com/api/v3/trades?symbol=BTCUSDT&limit=10"
    try:
        async with session.get(url, timeout=3) as resp:
            if resp.status == 200:
                trades = await resp.json()
                for t in trades:
                    qty = float(t["qty"])
                    if qty >= UMBRAL_BALLENA_BTC:
                        precio = float(t["price"])
                        tipo = "VENTA 🔴" if t["isBuyerMaker"] else "COMPRA 🟢"
                        return {"monto": qty, "precio": precio, "tipo": tipo, "exchange": "Binance"}
    except Exception:
        pass
    return None

# ==========================================
# 5. CICLO DE MONITOREO LÓGICA KALSHI
# ==========================================
async def ciclo_monitoreo():
    await bot.wait_until_ready()
    global manual_target, modo_manual, target_kalshi_auto, ultimo_intervalo_15m, ultima_senal_enviada
    
    canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")

    async with aiohttp.ClientSession() as session:
        while not bot.is_closed():
            try:
                if canal:
                    precio_btc = await obtener_precio_btc(session)

                    if precio_btc is not None:
                        # Calcular en qué ventana de 15 minutos estamos (00, 15, 30, 45)
                        ahora = datetime.utcnow()
                        minuto_bloque = (ahora.minute // 15) * 15
                        intervalo_actual = f"{ahora.hour}:{minuto_bloque:02d}"

                        # Si entramos en un nuevo bloque de 15m, CONGELAMOS el nuevo Price to Beat
                        if ultimo_intervalo_15m != intervalo_actual or target_kalshi_auto is None:
                            target_kalshi_auto = precio_btc
                            ultimo_intervalo_15m = intervalo_actual
                            ultima_senal_enviada = None  # Reiniciar señales para el nuevo bloque
                            print(f"🎯 [NUEVA VENTANA KALSHI] Target fijado para {intervalo_actual}: ${target_kalshi_auto:,.2f}")

                        # Determinar qué target usar (Manual o Auto-Kalshi)
                        target_activo = manual_target if modo_manual and manual_target else target_kalshi_auto

                        print(f"🔍 Monitoreando... BTC Coinbase: ${precio_btc:,.2f} | Target Kalshi: ${target_activo:,.2f}")

                        # CONDICIÓN DE ENTRADA (COMPRAR UP con confirmación de $5 por encima)
                        if precio_btc > (target_activo + MARGEN_MINIMO_CONFIRMACION):
                            accion = "COMPRAR UP 🚀"
                            diferencia = precio_btc - target_activo
                            identificador_senal = f"ENTRADA_{target_activo}_{intervalo_actual}"

                            if ultima_senal_enviada != identificador_senal:
                                embed = discord.Embed(
                                    title="🚨 NUEVA SEÑAL KALSHI BTC",
                                    color=discord.Color.green()
                                )
                                embed.add_field(name="Acción", value=f"🔥 **{accion}**", inline=False)
                                embed.add_field(name="Precio BTC (Coinbase)", value=f"${precio_btc:,.2f}", inline=True)
                                embed.add_field(name="Target a Vencer (Kalshi)", value=f"${target_activo:,.2f}", inline=True)
                                embed.add_field(name="Margen A Favor", value=f"+${diferencia:,.2f}", inline=False)

                                await canal.send(embed=embed)
                                print(f"⚡ [SEÑAL KALSHI] {accion} | Target: ${target_activo:,.2f} | BTC: ${precio_btc:,.2f}")
                                ultima_senal_enviada = identificador_senal

                        # CONDICIÓN DE SALIDA / STOP LOSS (Cae $15 por debajo del Target)
                        elif precio_btc < (target_activo - 15.0):
                            accion = "SALIR / CERRAR OPERACIÓN 🛑"
                            caida = target_activo - precio_btc
                            identificador_senal = f"SALIDA_{target_activo}_{intervalo_actual}"

                            if ultima_senal_enviada != identificador_senal and ultima_senal_enviada is not None and "ENTRADA" in str(ultima_senal_enviada):
                                embed = discord.Embed(
                                    title="⚠️ ALERTA DE SALIDA (STOP LOSS)",
                                    color=discord.Color.red()
                                )
                                embed.add_field(name="Acción", value=f"🚨 **{accion}**", inline=False)
                                embed.add_field(name="Precio BTC Actual", value=f"${precio_btc:,.2f}", inline=True)
                                embed.add_field(name="Target de Entrada", value=f"${target_activo:,.2f}", inline=True)
                                embed.add_field(name="Caída desde Target", value=f"-${caida:,.2f}", inline=False)

                                await canal.send(embed=embed)
                                print(f"🛑 Alerta de Salida enviada a Discord: -${caida:,.2f}")
                                ultima_senal_enviada = identificador_senal

                    # MONITOREO DE BALLENAS
                    ballena = await buscar_ballenas_binance(session)
                    if ballena:
                        monto_usd = ballena["monto"] * ballena["precio"]
                        embed_ballena = discord.Embed(
                            title=f"🐳 ALERTA DE BALLENA ({ballena['exchange']})",
                            color=discord.Color.gold()
                        )
                        embed_ballena.add_field(name="Operación", value=f"**{ballena['tipo']}**", inline=True)
                        embed_ballena.add_field(name="Cantidad", value=f"**{ballena['monto']:.2f} BTC** (~${monto_usd:,.2f})", inline=True)
                        embed_ballena.add_field(name="Precio Ejecutado", value=f"${ballena['precio']:,.2f}", inline=False)

                        await canal.send(embed_ballena)

            except Exception as e:
                print(f"⚠️ Error en ciclo de monitoreo: {e}")

            await asyncio.sleep(3)

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
