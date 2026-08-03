import os
import time
import json
import asyncio
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import aiohttp
import websockets
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
# 2. BASE DE DATOS LOCAL (MEMORIA)
# ==========================================
DB_FILE = "btc_memory.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS btc_prices (
            timestamp INTEGER PRIMARY KEY,
            price REAL,
            high REAL,
            low REAL
        )
    """)
    conn.commit()
    conn.close()

def guardar_precio_db(timestamp, price):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO btc_prices (timestamp, price, high, low)
        VALUES (?, ?, ?, ?)
    """, (timestamp, price, price, price))
    
    hace_30_dias = int(time.time()) - 2592000
    cursor.execute("DELETE FROM btc_prices WHERE timestamp < ?", (hace_30_dias,))
    conn.commit()
    conn.close()

def obtener_estadisticas_mes():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    hace_30_dias = int(time.time()) - 2592000
    cursor.execute("""
        SELECT MIN(price), MAX(price), AVG(price), COUNT(*)
        FROM btc_prices WHERE timestamp >= ?
    """, (hace_30_dias,))
    row = cursor.fetchone()
    conn.close()
    if row and row[3] > 0:
        return {"min": row[0], "max": row[1], "avg": row[2], "registros": row[3]}
    return None

init_db()

# ==========================================
# 3. CONFIGURACIÓN DE DISCORD Y VARIABLES
# ==========================================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

manual_target = None
modo_manual = False
target_kalshi_auto = None
precio_actual_global = 0.0

# Umbral de Ballenas (en BTC)
UMBRAL_BALLENA_BTC = 5.0  # Detecta órdenes mayores o iguales a 5 BTC (~$300k+)

MARGEN_MINIMO_CONFIRMACION = 15.0  
MARGEN_MAXIMO_ENTRADA = 60.0      
CAIDA_DESDE_MAXIMO_ALERTA = 25.0  
STOP_LOSS_ABS_CAIDA = 30.0        

COOLDOWN_ENTRADAS = 20            
COOLDOWN_RETROCESO = 15           

# ==========================================
# 4. FUNCIONES DE CÁLCULO DE RANGOS
# ==========================================
def calcular_niveles_kalshi(precio_actual):
    base_100 = round(precio_actual / 100) * 100
    techos = [base_100 + (100 * i) for i in range(1, 5)]
    if techos[0] <= precio_actual:
        techos = [t + 100 for t in techos]
        
    pisos = [base_100 - (100 * i) for i in range(1, 5)]
    if pisos[0] >= precio_actual:
        pisos = [p - 100 for p in pisos]
        
    return techos, pisos

# ==========================================
# 5. WEBSOCKET DE DETECCIÓN DE BALLENAS
# ==========================================
async def rastreador_ballenas():
    await bot.wait_until_ready()
    global precio_actual_global
    
    url = "wss://ws-feed.exchange.coinbase.com"
    suscribir_msg = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["matches"]
    }
    
    while not bot.is_closed():
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(suscribir_msg))
                print("🐋 Rastreando movimientos de ballenas en tiempo real...")
                
                async for mensaje in ws:
                    data = json.loads(mensaje)
                    if data.get("type") == "match":
                        size = float(data.get("size", 0))
                        price = float(data.get("price", 0))
                        side = data.get("side") # "buy" o "sell"
                        
                        precio_actual_global = price

                        if size >= UMBRAL_BALLENA_BTC:
                            canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")
                            if canal:
                                monto_usd = size * price
                                techos, pisos = calcular_niveles_kalshi(price)
                                
                                if side == "buy":
                                    color = discord.Color.green()
                                    titulo = "🐋 ¡COMPRA MASIVA DE BALLENA DETECTADA!"
                                    direccion = "📈 **IMPULSO ALCISTA PROBABLE**"
                                    sugerencia = f"Considera posiciones **YES / UP**. Objetivos inmediatos: **${techos[0]:,.0f}** o **${techos[1]:,.0f}**"
                                else:
                                    color = discord.Color.red()
                                    titulo = "🐋 ¡VENTA MASIVA DE BALLENA DETECTADA!"
                                    direccion = "📉 **PRESIÓN BAJISTA PROBABLE**"
                                    sugerencia = f"Considera posiciones **NO / DOWN** o salidas rápidas. Soportes: **${pisos[0]:,.0f}** o **${pisos[1]:,.0f}**"

                                embed = discord.Embed(title=titulo, color=color)
                                embed.add_field(name="Volumen Ejecutado", value=f"**{size:.2f} BTC** (~${monto_usd:,.2f} USD)", inline=False)
                                embed.add_field(name="Precio de Ejecución", value=f"${price:,.2f}", inline=True)
                                embed.add_field(name="Sesgo de Mercado", value=direccion, inline=True)
                                embed.add_field(name="🎯 Recomendación Kalshi", value=sugerencia, inline=False)
                                
                                await canal.send(embed=embed)

        except Exception as e:
            print(f"⚠️ Error en Websocket Ballenas: {e}")
            await asyncio.sleep(5)

# ==========================================
# 6. COMANDOS DISCORD
# ==========================================
@bot.command(name="rangos")
@bot.command(name="niveles")
async def estimar_rangos(ctx):
    precio = precio_actual_global if precio_actual_global > 0 else 63000.0
    techos, pisos = calcular_niveles_kalshi(precio)
    
    embed = discord.Embed(
        title="🎯 ESTIMACIÓN DE RANGOS / STRIKES PARA KALSHI",
        description=f"Precio Actual de BTC: **${precio:,.2f}**",
        color=discord.Color.purple()
    )
    
    text_techos = "".join([f"• **${t:,.0f}** (+${t - precio:,.2f})\n" for t in techos])
    embed.add_field(name="📈 Techos Estimados (Resistencias)", value=text_techos, inline=False)

    text_pisos = "".join([f"• **${p:,.0f}** (-${precio - p:,.2f})\n" for p in pisos])
    embed.add_field(name="📉 Pisos Estimados (Soportes)", value=text_pisos, inline=False)

    await ctx.send(embed=embed)

@bot.command(name="target")
async def set_target(ctx, valor: str = None):
    global manual_target, modo_manual
    if valor is None:
        estado = f"🎯 Target Manual: ${manual_target:,.2f}" if modo_manual else "🤖 Modo: AUTOMÁTICO"
        await ctx.send(f"ℹ️ {estado}")
        return

    if valor.lower() in ["auto", "reset"]:
        modo_manual = False
        manual_target = None
        await ctx.send("🤖 **Target restablecido a AUTOMÁTICO.**")
    else:
        try:
            precio = float(valor.replace(",", "").replace("$", ""))
            manual_target = precio
            modo_manual = True
            await ctx.send(f"🎯 **Target fijado en:** `${manual_target:,.2f}`")
        except ValueError:
            await ctx.send("❌ Formato incorrecto. Ejemplo: `!target 63142` ")

@bot.command(name="memoria")
async def ver_memoria(ctx):
    stats = obtener_estadisticas_mes()
    if not stats:
        await ctx.send("🧠 Recopilando datos...")
        return
    embed = discord.Embed(title="🧠 MEMORIA DE PRECIOS BTC (30 DÍAS)", color=discord.Color.blue())
    embed.add_field(name="Mínimo", value=f"${stats['min']:,.2f}", inline=True)
    embed.add_field(name="Máximo", value=f"${stats['max']:,.2f}", inline=True)
    embed.add_field(name="Promedio", value=f"${stats['avg']:,.2f}", inline=False)
    await ctx.send(embed=embed)

# ==========================================
# 7. CICLO DE MONITOREO PRINCIPAL
# ==========================================
async def ciclo_monitoreo():
    await bot.wait_until_ready()
    global manual_target, modo_manual, target_kalshi_auto, precio_actual_global
    
    canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")
    ultimo_bloque_1h = None
    maximo_precio_bloque = 0.0

    ultimo_envio_entrada = 0
    ultimo_envio_retroceso = 0
    ultimo_envio_salida = 0

    async with aiohttp.ClientSession() as session:
        while not bot.is_closed():
            try:
                if canal and precio_actual_global > 0:
                    precio_btc = precio_actual_global
                    tiempo_actual = time.time()
                    timestamp_int = int(tiempo_actual)

                    guardar_precio_db(timestamp_int, precio_btc)

                    bloque_actual_1h = (timestamp_int + 2) // 3600

                    if ultimo_bloque_1h != bloque_actual_1h or target_kalshi_auto is None:
                        target_kalshi_auto = precio_btc
                        ultimo_bloque_1h = bloque_actual_1h
                        maximo_precio_bloque = precio_btc
                        ultimo_envio_entrada = 0
                        ultimo_envio_retroceso = 0
                        ultimo_envio_salida = 0

                    target_activo = manual_target if modo_manual and manual_target else target_kalshi_auto

                    if target_activo:
                        if precio_btc > maximo_precio_bloque:
                            maximo_precio_bloque = precio_btc

                        diferencia = precio_btc - target_activo

                        # ENTRADA TÁCTICA
                        if MARGEN_MINIMO_CONFIRMACION <= diferencia <= MARGEN_MAXIMO_ENTRADA:
                            if (tiempo_actual - ultimo_envio_entrada) >= COOLDOWN_ENTRADAS:
                                techos, _ = calcular_niveles_kalshi(precio_btc)
                                embed = discord.Embed(title="🚨 SEÑAL DE COMPRA KALSHI (1H)", color=discord.Color.green())
                                embed.add_field(name="Acción Sugerida", value="🔥 **COMPRAR UP / YES**", inline=False)
                                embed.add_field(name="Precio BTC Actual", value=f"${precio_btc:,.2f}", inline=True)
                                embed.add_field(name="Target de Salida Sugerido", value=f"Buscar Strike en **${techos[0]:,.0f}**", inline=False)
                                await canal.send(embed=embed)
                                ultimo_envio_entrada = tiempo_actual

                        # STOP LOSS DEFINITIVO
                        elif precio_btc < (target_activo - STOP_LOSS_ABS_CAIDA):
                            if (tiempo_actual - ultimo_envio_salida) >= 30:
                                embed = discord.Embed(title="🛑 STOP LOSS - CERRAR POSICIÓN", color=discord.Color.red())
                                embed.add_field(name="Acción", value="🚨 **SALIR / CERRAR POSICIÓN**", inline=False)
                                embed.add_field(name="Precio BTC Actual", value=f"${precio_btc:,.2f}", inline=True)
                                await canal.send(embed=embed)
                                ultimo_envio_salida = tiempo_actual

            except Exception as e:
                print(f"⚠️ Error en monitoreo: {e}")

            await asyncio.sleep(1)

# ==========================================
# 8. INICIALIZACIÓN
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como: {bot.user.name}")
    bot.loop.create_task(rastreador_ballenas())
    bot.loop.create_task(ciclo_monitoreo())

async def main():
    async with bot:
        token = os.environ.get("DISCORD_BOT_TOKEN")
        if not token:
            raise ValueError("❌ Falta la variable DISCORD_BOT_TOKEN.")
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
