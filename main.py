import os
import time
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import aiohttp
import discord
from discord.ext import commands

# ==========================================
# 1. SERVIDOR WEB FALSO (Render 24/7)
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
# 2. CONFIGURACIÓN DE DISCORD Y ESTRATEGIA
# ==========================================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

manual_target = None
modo_manual = False
target_kalshi_auto = None
ultima_senal_enviada = None

# Parámetros Ajustados
UMBRAL_BALLENA_BTC = 5.0  
MARGEN_MINIMO_CONFIRMACION = 5.0   # Mínimo +$5 para confirmar entrada UP
MARGEN_MAXIMO_ENTRADA = 35.0       # Evita entrar si el salto ya fue mayor a +$35
CAIDA_DESDE_MAXIMO_ALERTA = 10.0   # Alerta de retroceso si cae $10 desde el pico local
STOP_LOSS_ABS_CAIDA = 15.0         # Cierre/Stop si cae $15 por debajo del Target

# ==========================================
# 3. COMANDOS DE DISCORD (!target)
# ==========================================
@bot.command(name="target")
async def set_target(ctx, valor: str = None):
    global manual_target, modo_manual, ultima_senal_enviada

    if valor is None:
        if modo_manual and manual_target:
            estado = f"🎯 Target Manual Actual: ${manual_target:,.2f}"
        elif target_kalshi_auto:
            estado = f"🤖 Target Kalshi Auto: ${target_kalshi_auto:,.2f}"
        else:
            estado = "🤖 Modo: AUTOMÁTICO (Obteniendo datos...)"
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
            
            await ctx.send(f"🎯 **Target fijado manualmente en:** `${manual_target:,.2f}`")
            print(f"📌 Target fijado manualmente en: {manual_target}")
        except ValueError:
            await ctx.send("❌ **Error:** Formato incorrecto. Ejemplo: `!target 63469.33`")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

# ==========================================
# 4. CONSULTAS DE API DE ALTA VELOCIDAD
# ==========================================
async def obtener_precio_btc(session):
    url = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
    try:
        async with session.get(url, timeout=2) as resp:
            if resp.status == 200:
                data = await resp.json()
                return float(data["data"]["amount"])
    except Exception:
        pass
    return None

async def obtener_price_to_beat_kalshi(session):
    url = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=900"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with session.get(url, headers=headers, timeout=2) as resp:
            if resp.status == 200:
                candles = await resp.json()
                if candles:
                    candles_sorted = sorted(candles, key=lambda x: x[0], reverse=True)
                    return float(candles_sorted[0][3])
    except Exception as e:
        print(f"⚠️ Error al obtener Target de Kalshi: {e}")
    return None

async def buscar_ballenas_binance(session):
    url = "https://api.binance.com/api/v3/trades?symbol=BTCUSDT&limit=10"
    try:
        async with session.get(url, timeout=2) as resp:
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
# 5. CICLO DE MONITOREO CON ALERTA DE RETROCESO
# ==========================================
async def ciclo_monitoreo():
    await bot.wait_until_ready()
    global manual_target, modo_manual, target_kalshi_auto, ultima_senal_enviada
    
    canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")
    ultimo_bloque_15m = None
    maximo_precio_bloque = 0.0

    async with aiohttp.ClientSession() as session:
        while not bot.is_closed():
            try:
                if canal:
                    precio_btc = await obtener_precio_btc(session)

                    if precio_btc is not None:
                        # Anticipación de 5 segundos
                        timestamp_anticipado = int(time.time()) + 5
                        bloque_actual = timestamp_anticipado // 900

                        # Detección de nuevo bloque
                        if ultimo_bloque_15m != bloque_actual or target_kalshi_auto is None:
                            target_kalshi_auto = precio_btc
                            
                            target_vela = await obtener_price_to_beat_kalshi(session)
                            if target_vela:
                                target_kalshi_auto = target_vela

                            ultimo_bloque_15m = bloque_actual
                            ultima_senal_enviada = None
                            maximo_precio_bloque = precio_btc
                            print(f"⚡ [NUEVO BLOQUE] Target Fijado: ${target_kalshi_auto:,.2f}")

                        target_activo = manual_target if modo_manual and manual_target else target_kalshi_auto

                        if target_activo:
                            # Actualizar el pico más alto alcanzado en este bloque
                            if precio_btc > maximo_precio_bloque:
                                maximo_precio_bloque = precio_btc

                            diferencia = precio_btc - target_activo
                            print(f"🔍 BTC: ${precio_btc:,.2f} | Max Pico: ${maximo_precio_bloque:,.2f} | Target: ${target_activo:,.2f}")

                            # 1. SEÑAL DE ENTRADA (COMPRAR UP)
                            if MARGEN_MINIMO_CONFIRMACION <= diferencia <= MARGEN_MAXIMO_ENTRADA:
                                accion = "COMPRAR UP 🚀"
                                identificador_senal = f"ENTRADA_{target_activo}_{bloque_actual}"

                                if ultima_senal_enviada != identificador_senal:
                                    embed = discord.Embed(
                                        title="🚨 NUEVA SEÑAL KALSHI BTC",
                                        color=discord.Color.green()
                                    )
                                    embed.add_field(name="Acción", value=f"🔥 **{accion}**", inline=False)
                                    embed.add_field(name="Precio BTC (Coinbase)", value=f"${precio_btc:,.2f}", inline=True)
                                    embed.add_field(name="Target a Vencer", value=f"${target_activo:,.2f}", inline=True)
                                    embed.add_field(name="Margen A Favor", value=f"+${diferencia:,.2f}", inline=False)

                                    await canal.send(embed=embed)
                                    print(f"⚡ [SEÑAL ENTRADA] {accion} | BTC: ${precio_btc:,.2f}")
                                    ultima_senal_enviada = identificador_senal

                            # 2. ALERTA DE RETROCESO DESDE EL PICO (ALERTA DE SEGURIDAD)
                            caida_desde_pico = maximo_precio_bloque - precio_btc
                            identificador_retroceso = f"RETROCESO_{maximo_precio_bloque}_{bloque_actual}"

                            if (caida_desde_pico >= CAIDA_DESDE_MAXIMO_ALERTA and 
                                ultima_senal_enviada is not None and "ENTRADA" in str(ultima_senal_enviada) and
                                ultima_senal_enviada != identificador_retroceso):
                                
                                embed = discord.Embed(
                                    title="⚠️ ALERTA DE RETROCESO BRUSCO",
                                    color=discord.Color.gold()
                                )
                                embed.add_field(name="Aviso", value="📉 **El precio cayó $10+ desde su punto más alto.**", inline=False)
                                embed.add_field(name="Pico Máximo", value=f"${maximo_precio_bloque:,.2f}", inline=True)
                                embed.add_field(name="Precio Actual", value=f"${precio_btc:,.2f}", inline=True)
                                embed.add_field(name="Retroceso Detectado", value=f"-${caida_desde_pico:,.2f}", inline=False)
                                embed.add_field(name="Recomendación", value="Tomar ganancias o cerrar posición.", inline=False)

                                await canal.send(embed=embed)
                                print(f"⚠️ [ALERTA RETROCESO] Caída de -${caida_desde_pico:,.2f} desde pico.")
                                ultima_senal_enviada = identificador_retroceso

                            # 3. ALERTA DE STOP LOSS DEFINITIVO
                            elif precio_btc < (target_activo - STOP_LOSS_ABS_CAIDA):
                                accion = "SALIR / CERRAR OPERACIÓN 🛑"
                                caida = target_activo - precio_btc
                                identificador_salida = f"SALIDA_{target_activo}_{bloque_actual}"

                                if ultima_senal_enviada != identificador_salida and ultima_senal_enviada is not None:
                                    embed = discord.Embed(
                                        title="🛑 STOP LOSS / CERRAR POSICIÓN",
                                        color=discord.Color.red()
                                    )
                                    embed.add_field(name="Acción", value=f"🚨 **{accion}**", inline=False)
                                    embed.add_field(name="Precio BTC Actual", value=f"${precio_btc:,.2f}", inline=True)
                                    embed.add_field(name="Target de Entrada", value=f"${target_activo:,.2f}", inline=True)
                                    embed.add_field(name="Pérdida", value=f"-${caida:,.2f}", inline=False)

                                    await canal.send(embed=embed)
                                    print(f"🛑 [STOP LOSS] Salida enviada a Discord.")
                                    ultima_senal_enviada = identificador_salida

                    # Detección de ballenas
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

                else:
                    print("⚠️ No se encontró el canal 'alertas-kalshi'")

            except Exception as e:
                print(f"⚠️ Error en ciclo de monitoreo: {e}")

            # Consulta cada 1 segundo para máxima velocidad
            await asyncio.sleep(1)

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
