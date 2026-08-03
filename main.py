import os
import time
import json
import asyncio
import sqlite3
import threading
from collections import deque
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

# Deque para guardar los últimos 60 precios (1 precio por segundo aprox)
historial_corto = deque(maxlen=60)

# Umbral de Ballenas (en BTC)
UMBRAL_BALLENA_BTC = 5.0  # Detecta órdenes >= 5 BTC (~$300k+)

# PARÁMETROS PARA SCALPING RÁPIDO (1H)
IMPULSO_RAPIDO_USD = 18.0       # Cambio rápido de $18+ activa señal de micro-entrada
TAKE_PROFIT_SCALP_USD = 15.0    # Objetivo de ganancia rápida para salir
STOP_LOSS_SCALP_USD = 20.0      # Stop loss para micro-operaciones
COOLDOWN_SCALPING = 45          # 45 segundos entre entradas rápidas

posicion_actual = None          # Guarda si estamos en "BUY" o "SELL"
precio_entrada_posicion = 0.0
ultimo_envio_scalp = 0

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
                        side = data.get("side")  # "buy" o "sell"
                        
                        precio_actual_global = price
                        historial_corto.append(price)

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
# 6. COMANDOS DISCORD (CORREGIDOS)
# ==========================================
@bot.command(name="rangos", aliases=["niveles"])
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

@bot.command(name="memoria", aliases=["stats"])
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

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

# ==========================================
# 7. CICLO DE MONITOREO PRINCIPAL Y SCALPING
# ==========================================
async def ciclo_monitoreo():
    await bot.wait_until_ready()
    global manual_target, modo_manual, target_kalshi_auto, precio_actual_global
    global posicion_actual, precio_entrada_posicion, ultimo_envio_scalp
    
    canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")
    ultimo_bloque_1h = None

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
                        posicion_actual = None

                    # ----------------------------------------------------
                    # A. LÓGICA DE GESTIÓN DE POSICIÓN ABIERTA (TAKE PROFIT / STOP LOSS)
                    # ----------------------------------------------------
                    if posicion_actual == "BUY":
                        ganancia = precio_btc - precio_entrada_posicion
                        
                        # TAKE PROFIT
                        if ganancia >= TAKE_PROFIT_SCALP_USD:
                            embed = discord.Embed(title="💰 TAKE PROFIT - CERRAR GANANCIA (BUY)", color=discord.Color.gold())
                            embed.add_field(name="Acción", value="✅ **VENDER / CERRAR POSICIÓN AHORA**", inline=False)
                            embed.add_field(name="Ganancia Aproximada", value=f"+${ganancia:,.2f} USD", inline=True)
                            embed.add_field(name="Precio Actual", value=f"${precio_btc:,.2f}", inline=True)
                            await canal.send(embed=embed)
                            posicion_actual = None
                            
                        # STOP LOSS
                        elif ganancia <= -STOP_LOSS_SCALP_USD:
                            embed = discord.Embed(title="🛑 STOP LOSS - CERRAR SCALP (BUY)", color=discord.Color.red())
                            embed.add_field(name="Acción", value="🚨 **SALIR DE LA POSICIÓN**", inline=False)
                            embed.add_field(name="Pérdida", value=f"-${abs(ganancia):,.2f} USD", inline=True)
                            embed.add_field(name="Precio Actual", value=f"${precio_btc:,.2f}", inline=True)
                            await canal.send(embed=embed)
                            posicion_actual = None

                    elif posicion_actual == "SELL":
                        ganancia = precio_entrada_posicion - precio_btc
                        
                        # TAKE PROFIT
                        if ganancia >= TAKE_PROFIT_SCALP_USD:
                            embed = discord.Embed(title="💰 TAKE PROFIT - CERRAR GANANCIA (SELL)", color=discord.Color.gold())
                            embed.add_field(name="Acción", value="✅ **VENDER / CERRAR POSICIÓN AHORA**", inline=False)
                            embed.add_field(name="Ganancia Aproximada", value=f"+${ganancia:,.2f} USD", inline=True)
                            embed.add_field(name="Precio Actual", value=f"${precio_btc:,.2f}", inline=True)
                            await canal.send(embed=embed)
                            posicion_actual = None
                            
                        # STOP LOSS
                        elif ganancia <= -STOP_LOSS_SCALP_USD:
                            embed = discord.Embed(title="🛑 STOP LOSS - CERRAR SCALP (SELL)", color=discord.Color.red())
                            embed.add_field(name="Acción", value="🚨 **SALIR DE LA POSICIÓN**", inline=False)
                            embed.add_field(name="Pérdida", value=f"-${abs(ganancia):,.2f} USD", inline=True)
                            embed.add_field(name="Precio Actual", value=f"${precio_btc:,.2f}", inline=True)
                            await canal.send(embed=embed)
                            posicion_actual = None

                    # ----------------------------------------------------
                    # B. LÓGICA DE BÚSQUEDA DE NUEVAS ENTRADAS (SCALPING)
                    # ----------------------------------------------------
                    elif posicion_actual is None and len(historial_corto) >= 15:
                        precio_hace_30s = historial_corto[0]
                        variacion = precio_btc - precio_hace_30s

                        if (tiempo_actual - ultimo_envio_scalp) >= COOLDOWN_SCALPING:
                            techos, pisos = calcular_niveles_kalshi(precio_btc)

                            # NUEVA ENTRADA EN COMPRA (UP)
                            if variacion >= IMPULSO_RAPIDO_USD:
                                posicion_actual = "BUY"
                                precio_entrada_posicion = precio_btc
                                ultimo_envio_scalp = tiempo_actual

                                embed = discord.Embed(title="⚡ SEÑAL DE SCALPING RÁPIDO (COMPRA UP)", color=discord.Color.green())
                                embed.add_field(name="Acción Sugerida", value="🟢 **COMPRAR YES / UP**", inline=False)
                                embed.add_field(name="Precio Entrada", value=f"${precio_btc:,.2f}", inline=True)
                                embed.add_field(name="Impulso Detectado", value=f"+${variacion:,.2f} en 30s", inline=True)
                                embed.add_field(name="🎯 Target Rápido Kalshi", value=f"Objetivo de salida: **${precio_btc + TAKE_PROFIT_SCALP_USD:,.2f}** (o Strike **${techos[0]:,.0f}**)", inline=False)
                                await canal.send(embed=embed)

                            # NUEVA ENTRADA EN VENTA (DOWN)
                            elif variacion <= -IMPULSO_RAPIDO_USD:
                                posicion_actual = "SELL"
                                precio_entrada_posicion = precio_btc
                                ultimo_envio_scalp = tiempo_actual

                                embed = discord.Embed(title="⚡ SEÑAL DE SCALPING RÁPIDO (VENTA DOWN)", color=discord.Color.red())
                                embed.add_field(name="Acción Sugerida", value="🔴 **COMPRAR NO / DOWN**", inline=False)
                                embed.add_field(name="Precio Entrada", value=f"${precio_btc:,.2f}", inline=True)
                                embed.add_field(name="Caída Detectada", value=f"-${abs(variacion):,.2f} en 30s", inline=True)
                                embed.add_field(name="🎯 Target Rápido Kalshi", value=f"Objetivo de salida: **${precio_btc - TAKE_PROFIT_SCALP_USD:,.2f}** (o Piso **${pisos[0]:,.0f}**)", inline=False)
                                await canal.send(embed=embed)

            except Exception as e:
                print(f"⚠️ Error en monitoreo: {e}")

            await asyncio.sleep(1)

# ==========================================
# 8. INICIALIZACIÓN
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado correctamente como: {bot.user.name}")
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
