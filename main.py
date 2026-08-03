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
# 2. BASE DE DATOS LOCAL
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

historial_corto = deque(maxlen=60)
UMBRAL_BALLENA_BTC = 5.0
INVERSION_FIX_USD = 10.0  # Inversión exacta de $10 USD

# ==========================================
# 4. LÓGICA DE ESTIMACIÓN KALSHI (STRIKES 100 IN 100)
# ==========================================
def calcular_prediccion_kalshi(precio_actual):
    """Calcula el target exacto de cierre (Arriba de X o Abajo de Y)"""
    base_100 = round(precio_actual / 100) * 100
    
    # Calcular tendencia reciente (último minuto)
    if len(historial_corto) >= 10:
        momentum = precio_actual - historial_corto[0]
    else:
        momentum = 0.0

    # Estimación de sesgo alcista o bajista
    if momentum >= 0:
        direccion = "ARRIBA (UP / YES)"
        # Niveles superiores para Kalshi ($63,500 / $63,600 / $63,700, etc.)
        strike_principal = base_100 if base_100 > precio_actual else base_100 + 100
        strike_seguro = strike_principal - 100
        strike_agresivo = strike_principal + 100
        
        recomendaciones = {
            "direccion": direccion,
            "target_principal": f"BTC estará **POR ENCIMA DE ${strike_principal:,.0f}**",
            "strike_seguro": f"Arriba de ${strike_seguro:,.0f} (Costo ~$0.68) ➔ Ganancia: +$4.70 USD con $10",
            "strike_balanceado": f"Arriba de ${strike_principal:,.0f} (Costo ~$0.45) ➔ Ganancia: +$12.20 USD con $10",
            "strike_agresivo": f"Arriba de ${strike_agresivo:,.0f} (Costo ~$0.25) ➔ Ganancia: +$30.00 USD con $10"
        }
    else:
        direccion = "ABAJO (DOWN / NO)"
        # Niveles inferiores para Kalshi ($64,000 / $63,900 / $63,800, etc.)
        strike_principal = base_100 if base_100 < precio_actual else base_100 - 100
        strike_seguro = strike_principal + 100
        strike_agresivo = strike_principal - 100
        
        recomendaciones = {
            "direccion": direccion,
            "target_principal": f"BTC estará **POR DEBAJO DE ${strike_seguro:,.0f}**",
            "strike_seguro": f"Abajo de ${strike_seguro:,.0f} (Costo ~$0.68) ➔ Ganancia: +$4.70 USD con $10",
            "strike_balanceado": f"Abajo de ${strike_principal:,.0f} (Costo ~$0.45) ➔ Ganancia: +$12.20 USD con $10",
            "strike_agresivo": f"Abajo de ${strike_agresivo:,.0f} (Costo ~$0.25) ➔ Ganancia: +$30.00 USD con $10"
        }
        
    return recomendaciones

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
                        side = data.get("side")
                        
                        precio_actual_global = price
                        historial_corto.append(price)

                        if size >= UMBRAL_BALLENA_BTC:
                            canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")
                            if canal:
                                monto_usd = size * price
                                recs = calcular_prediccion_kalshi(price)
                                
                                color = discord.Color.green() if side == "buy" else discord.Color.red()
                                titulo = "🐋 ¡IMPACTO DE BALLENA EN EL PRECIO!"
                                
                                embed = discord.Embed(title=titulo, color=color)
                                embed.add_field(name="Orden Ejecutada", value=f"**{size:.2f} BTC** (~${monto_usd:,.2f} USD)", inline=False)
                                embed.add_field(name="Precio BTC", value=f"${price:,.2f}", inline=True)
                                embed.add_field(name="🎯 Recomendación $10 USD", value=recs["target_principal"], inline=False)
                                embed.add_field(name="Opción Balanceada", value=recs["strike_balanceado"], inline=False)
                                
                                await canal.send(embed=embed)

        except Exception as e:
            print(f"⚠️ Error en Websocket Ballenas: {e}")
            await asyncio.sleep(5)

# ==========================================
# 6. COMANDOS DISCORD (PROYECCIÓN A LAS :00)
# ==========================================
@bot.command(name="proyeccion", aliases=["hora", "cierre", "target"])
async def estimar_cierre_hora(ctx):
    """Muestra el Strike recomendado para el cierre de la hora actual con $10 USD"""
    precio = precio_actual_global if precio_actual_global > 0 else 63000.0
    
    minuto_actual = time.strftime("%M")
    minutos_restantes = 60 - int(minuto_actual)
    proxima_hora = (int(time.strftime("%I")) % 12) + 1
    ampm = time.strftime("%p")
    
    recs = calcular_prediccion_kalshi(precio)
    
    embed = discord.Embed(
        title=f"⏳ PREPARACIÓN CIERRE DE VELA ({proxima_hora}:00 {ampm})",
        description=f"Faltan **{minutos_restantes} minutos** para el cierre a las **{proxima_hora}:00 {ampm}**.\nInversión: **$10 USD**",
        color=discord.Color.gold()
    )
    
    embed.add_field(name="Precio BTC Actual", value=f"**${precio:,.2f}**", inline=True)
    embed.add_field(name="Predicción Principal Kalshi", value=f"🎯 {recs['target_principal']}", inline=False)
    
    embed.add_field(name="🟢 Opción Segura (Bajo Riesgo)", value=recs["strike_seguro"], inline=False)
    embed.add_field(name="🟡 Opción Recomendada (Rendimiento Medio)", value=recs["strike_balanceado"], inline=False)
    embed.add_field(name="🔴 Opción Agresiva (Alto Rendimiento)", value=recs["strike_agresivo"], inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="rangos", aliases=["niveles"])
async def estimar_rangos(ctx):
    precio = precio_actual_global if precio_actual_global > 0 else 63000.0
    base_100 = round(precio / 100) * 100
    
    embed = discord.Embed(
        title="🎯 STRIKES DISPONIBLES EN KALSHI",
        description=f"Precio BTC Actual: **${precio:,.2f}**",
        color=discord.Color.purple()
    )
    
    techos = [f"• BTC **Arriba de ${base_100 + (100 * i):,.0f}**" for i in range(1, 4)]
    pisos = [f"• BTC **Debajo de ${base_100 - (100 * i):,.0f}**" for i in range(0, 3)]
    
    embed.add_field(name="📈 Contratos UP / YES", value="\n".join(techos), inline=False)
    embed.add_field(name="📉 Contratos DOWN / NO", value="\n".join(pisos), inline=False)

    await ctx.send(embed=embed)

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
# 7. CICLO PRINCIPAL DE ALERTAS CADA HORA (:00)
# ==========================================
async def ciclo_monitoreo():
    await bot.wait_until_ready()
    global precio_actual_global
    
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

                    # ----------------------------------------------------
                    # ALERTA AUTOMÁTICA AL CAMBIAR LA HORA (10:00, 11:00, 12:00)
                    # ----------------------------------------------------
                    if ultimo_bloque_1h != bloque_actual_1h:
                        ultimo_bloque_1h = bloque_actual_1h
                        proxima_hora = (int(time.strftime("%I")) % 12) + 1
                        ampm = time.strftime("%p")

                        recs = calcular_prediccion_kalshi(precio_btc)

                        embed = discord.Embed(
                            title=f"🚨 RECOMENDACIÓN DE ENTRADA KALSHI ($10 USD) - CIERRE {proxima_hora}:00 {ampm}",
                            description=f"Precio Apertura de la Hora: **${precio_btc:,.2f}**\nOperación recomendada para cerrar a las **{proxima_hora}:00 {ampm}**",
                            color=discord.Color.teal()
                        )
                        
                        embed.add_field(name="🎯 Predicción Principal", value=recs["target_principal"], inline=False)
                        embed.add_field(name="🟢 Opción Segura", value=recs["strike_seguro"], inline=False)
                        embed.add_field(name="🟡 Opción Balanceada", value=recs["strike_balanceado"], inline=False)
                        embed.add_field(name="🔴 Opción Agresiva", value=recs["strike_agresivo"], inline=False)
                        embed.set_footer(text="Usa !proyeccion en cualquier momento de la hora para actualizar el Target.")
                        
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
