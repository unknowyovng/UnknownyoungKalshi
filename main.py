import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import discord
from discord.ext import commands

# ==========================================
# 1. SERVIDOR WEB FALSO (Render Gratis 24/7)
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
ultima_senal_enviada = None

# Umbral para considerar una orden como "Ballena" (5 BTC o más)
UMBRAL_BALLENA_BTC = 5.0  

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
        ultima_senal_enviada = None
        await ctx.send("🤖 **Target restablecido a MODO AUTOMÁTICO.**")
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
            await ctx.send("❌ **Error:** Formato incorrecto. Ejemplo: `!target 63629.00`")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

# ==========================================
# 4. CONSULTA DE PRECIOS Y BALLENAS
# ==========================================
def obtener_precio_btc():
    """Obtiene el precio spot en tiempo real de Bitcoin en Coinbase"""
    try:
        url = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return float(response.json()["data"]["amount"])
    except Exception as e:
        print(f"⚠️ Error obteniendo precio Coinbase: {e}")
    return None

def buscar_ballenas_binance():
    """Rastrea grandes transacciones recientes en Binance"""
    try:
        url = "https://api.binance.com/api/v3/trades?symbol=BTCUSDT&limit=10"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            trades = response.json()
            for t in trades:
                qty = float(t["qty"])
                if qty >= UMBRAL_BALLENA_BTC:
                    precio = float(t["price"])
                    tipo = "VENTA 🔴" if t["isBuyerMaker"] else "COMPRA 🟢"
                    return {"monto": qty, "precio": precio, "tipo": tipo, "exchange": "Binance"}
    except Exception as e:
        print(f"⚠️ Error rastreando ballenas Binance: {e}")
    return None

def obtener_target_auto():
    return 63456.97

# ==========================================
# 5. CICLO DE MONITOREO (ENTRADAS, SALIDAS Y BALLENAS)
# ==========================================
async def ciclo_monitoreo():
    await bot.wait_until_ready()
    global manual_target, modo_manual, ultima_senal_enviada
    
    canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")

    while not bot.is_closed():
        try:
            if canal:
                # --------------------------------------------------
                # A. MONITOREO DE PRECIO, ENTRADAS Y SALIDAS
                # --------------------------------------------------
                precio_btc = obtener_precio_btc()

                if precio_btc is not None:
                    target_calculado_auto = obtener_target_auto()
                    target_activo = manual_target if modo_manual and manual_target else target_calculado_auto

                    print(f"🔍 Monitoreando... BTC Coinbase: ${precio_btc:,.2f} | Target Activo: ${target_activo:,.2f}")

                    # 1. CONDICIÓN DE ENTRADA (COMPRAR UP)
                    if precio_btc > target_activo:
                        accion = "COMPRAR UP 🚀"
                        diferencia = precio_btc - target_activo
                        identificador_senal = f"ENTRADA_{target_activo}"

                        if ultima_senal_enviada != identificador_senal:
                            embed = discord.Embed(
                                title="🚨 NUEVA SEÑAL KALSHI BTC",
                                color=discord.Color.green()
                            )
                            embed.add_field(name="Acción", value=f"🔥 **{accion}**", inline=False)
                            embed.add_field(name="Precio BTC (Coinbase)", value=f"${precio_btc:,.2f}", inline=True)
                            embed.add_field(name="Target a Vencer", value=f"${target_activo:,.2f}", inline=True)
                            embed.add_field(name="Margen A favor", value=f"+${diferencia:,.2f}", inline=False)

                            await canal.send(embed=embed)
                            print(f"📢 Señal de Entrada enviada a Discord: {accion}")
                            ultima_senal_enviada = identificador_senal

                    # 2. CONDICIÓN DE SALIDA / STOP LOSS (Cuando cae $20 por debajo del Target)
                    elif precio_btc < (target_activo - 20.0):
                        accion = "SALIR / CERRAR OPERACIÓN 🛑"
                        caida = target_activo - precio_btc
                        identificador_senal = f"SALIDA_{target_activo}"

                        # Solo envía alerta de salida si veníamos de una ENTRADA activa
                        if ultima_senal_enviada != identificador_senal and ultima_senal_enviada is not None and "ENTRADA" in str(ultima_senal_enviada):
                            embed = discord.Embed(
                                title="⚠️ ALERTA DE SALIDA (INVALIDACIÓN / STOP LOSS)",
                                color=discord.Color.red()
                            )
                            embed.add_field(name="Acción", value=f"🚨 **{accion}**", inline=False)
                            embed.add_field(name="Precio BTC Actual", value=f"${precio_btc:,.2f}", inline=True)
                            embed.add_field(name="Target de Entrada", value=f"${target_activo:,.2f}", inline=True)
                            embed.add_field(name="Caída desde Target", value=f"-${caida:,.2f}", inline=False)
                            embed.add_field(name="Recomendación", value="Cerrar la posición para recortar pérdidas antes de un mayor retroceso.", inline=False)

                            await canal.send(embed=embed)
                            print(f"🛑 Alerta de Salida enviada a Discord: -${caida:,.2f}")
                            ultima_senal_enviada = identificador_senal

                # --------------------------------------------------
                # B. MONITOREO DE BALLENAS (BINANCE / COINBASE)
                # --------------------------------------------------
                ballena = buscar_ballenas_binance()
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
                    print(f"🐳 Ballena detectada: {ballena['monto']} BTC en {ballena['exchange']}")

            else:
                print("⚠️ No se encontró el canal 'alertas-kalshi'")

        except Exception as e:
            print(f"⚠️ Error en ciclo de monitoreo: {e}")

        # Frecuencia de escaneo
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
