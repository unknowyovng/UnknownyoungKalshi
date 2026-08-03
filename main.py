import os
import time
import json
import asyncio
import sqlite3
import threading
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from zoneinfo import ZoneInfo  # Manejo exacto de zona horaria local
import aiohttp
import websockets
import discord
from discord.ext import commands

# Configuración de Zona Horaria (Hora del Este / Florida EDT-EST)
ZONA_HORARIA_LOCAL = ZoneInfo("America/New_York")

def obtener_hora_local():
    """Retorna un objeto datetime con la hora exacta de la zona Este"""
    return datetime.now(ZONA_HORARIA_LOCAL)

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
# 2. BASE DE DATOS LOCAL CON SOPORTE OHLC (VELAS)
# ==========================================
DB_FILE = "btc_memory.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Guardar picos (high), bajos (low), apertura (open) y cierre (close) por bloque horario
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS btc_hourly_candles (
            hour_timestamp INTEGER PRIMARY KEY,
            open_price REAL,
            high_price REAL,
            low_price REAL,
            close_price REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS btc_prices (
            timestamp INTEGER PRIMARY KEY,
            price REAL
        )
    """)
    conn.commit()
    conn.close()

def actualizar_vela_hora_db(hour_ts, open_p, high_p, low_p, close_p):
    """Guarda o actualiza la vela horaria con su verdadero High y Low"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO btc_hourly_candles (hour_timestamp, open_price, high_price, low_price, close_price)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(hour_timestamp) DO UPDATE SET
            high_price = MAX(high_price, excluded.high_price),
            low_price = MIN(low_price, excluded.low_price),
            close_price = excluded.close_price
    """, (hour_ts, open_p, high_p, low_p, close_p))
    
    # Mantener máximo 30 días de historial
    hace_30_dias = int(time.time()) - 2592000
    cursor.execute("DELETE FROM btc_hourly_candles WHERE hour_timestamp < ?", (hace_30_dias,))
    conn.commit()
    conn.close()

def obtener_promedio_rango_horario():
    """Calcula el rango promedio (High - Low) de las últimas velas procesadas"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT AVG(high_price - low_price)
        FROM (
            SELECT high_price, low_price 
            FROM btc_hourly_candles 
            ORDER BY hour_timestamp DESC 
            LIMIT 24
        )
    """)
    row = cursor.fetchone()
    conn.close()
    if row and row[0] is not None and row[0] > 0:
        return row[0]
    return 150.0  # Rango por defecto ($150 USD) si hay pocos datos

init_db()

# ==========================================
# 3. CONFIGURACIÓN DE DISCORD Y VARIABLES EN VIVO
# ==========================================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

precio_actual_global = 0.0

# Tracking de Vela Horaria Actual
vela_actual = {
    "hour_timestamp": None,
    "open": 0.0,
    "high": 0.0,
    "low": 0.0,
    "close": 0.0
}

historial_corto = deque(maxlen=60)
UMBRAL_BALLENA_BTC = 5.0

def actualizar_tracking_vela(price):
    """Registra en tiempo real los picos (high) y bajos (low) de la vela actual"""
    global vela_actual
    now_ts = int(time.time())
    hour_ts = (now_ts // 3600) * 3600
    
    if vela_actual["hour_timestamp"] != hour_ts:
        # Nueva hora iniciada
        vela_actual["hour_timestamp"] = hour_ts
        vela_actual["open"] = price
        vela_actual["high"] = price
        vela_actual["low"] = price
        vela_actual["close"] = price
    else:
        # Actualización de la hora en curso
        if price > vela_actual["high"]:
            vela_actual["high"] = price
        if price < vela_actual["low"]:
            vela_actual["low"] = price
        vela_actual["close"] = price
        
    actualizar_vela_hora_db(hour_ts, vela_actual["open"], vela_actual["high"], vela_actual["low"], vela_actual["close"])

# ==========================================
# 4. LÓGICA KALSHI BASADA EN VOLATILIDAD Y OHLC
# ==========================================
def calcular_prediccion_kalshi(precio_actual):
    """Calcula el target considerando la Apertura, Máximo, Mínimo y Rango Promedio"""
    base_100 = round(precio_actual / 100) * 100
    rango_promedio = obtener_promedio_rango_horario()
    
    open_p = vela_actual["open"] if vela_actual["open"] > 0 else precio_actual
    high_p = vela_actual["high"] if vela_actual["high"] > 0 else precio_actual
    low_p = vela_actual["low"] if vela_actual["low"] > 0 else precio_actual
    
    momentum_vela = precio_actual - open_p

    if momentum_vela >= 0:
        direccion = "ARRIBA (UP / YES)"
        strike_principal = base_100 if base_100 > precio_actual else base_100 + 100
        strike_seguro = strike_principal - 100
        strike_agresivo = strike_principal + 100
        
        recomendaciones = {
            "direccion": direccion,
            "target_principal": f"BTC estará **POR ENCIMA DE ${strike_principal:,.0f}**",
            "strike_seguro": f"Arriba de ${strike_seguro:,.0f} (Costo ~$0.68) ➔ Ganancia: +$4.70 USD con $10",
            "strike_balanceado": f"Arriba de ${strike_principal:,.0f} (Costo ~$0.45) ➔ Ganancia: +$12.20 USD con $10",
            "strike_agresivo": f"Arriba de ${strike_agresivo:,.0f} (Costo ~$0.25) ➔ Ganancia: +$30.00 USD con $10",
            "pico_alto": high_p,
            "pico_bajo": low_p,
            "rango_promedio": rango_promedio
        }
    else:
        direccion = "ABAJO (DOWN / NO)"
        strike_principal = base_100 if base_100 < precio_actual else base_100 - 100
        strike_seguro = strike_principal + 100
        strike_agresivo = strike_principal - 100
        
        recomendaciones = {
            "direccion": direccion,
            "target_principal": f"BTC estará **POR DEBAJO DE ${strike_seguro:,.0f}**",
            "strike_seguro": f"Abajo de ${strike_seguro:,.0f} (Costo ~$0.68) ➔ Ganancia: +$4.70 USD con $10",
            "strike_balanceado": f"Abajo de ${strike_principal:,.0f} (Costo ~$0.45) ➔ Ganancia: +$12.20 USD con $10",
            "strike_agresivo": f"Abajo de ${strike_agresivo:,.0f} (Costo ~$0.25) ➔ Ganancia: +$30.00 USD con $10",
            "pico_alto": high_p,
            "pico_bajo": low_p,
            "rango_promedio": rango_promedio
        }
        
    return recomendaciones

# ==========================================
# 5. WEBSOCKET DE DETECCIÓN DE BALLENAS Y PRECIO EN VIVO
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
                print("🐋 Rastreando movimientos de ballenas y picos/bajos en tiempo real...")
                
                async for mensaje in ws:
                    data = json.loads(mensaje)
                    if data.get("type") == "match":
                        size = float(data.get("size", 0))
                        price = float(data.get("price", 0))
                        side = data.get("side")
                        
                        precio_actual_global = price
                        historial_corto.append(price)
                        actualizar_tracking_vela(price)  # Mantiene registrado High/Low de la vela

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
# 6. COMANDOS DISCORD DE MONITOREO Y PROYECCIÓN
# ==========================================
@bot.command(name="proyeccion", aliases=["hora", "cierre", "target"])
async def estimar_cierre_hora(ctx):
    """Muestra la proyección con datos de Máximos y Mínimos de la vela en curso"""
    precio = precio_actual_global if precio_actual_global > 0 else 63000.0
    
    ahora_local = obtener_hora_local()
    minuto_actual = ahora_local.minute
    minutos_restantes = 60 - minuto_actual
    
    timestamp_proxima = ahora_local.timestamp() + (minutos_restantes * 60)
    proxima_hora_dt = datetime.fromtimestamp(timestamp_proxima, tz=ZONA_HORARIA_LOCAL)
    texto_proxima_hora = proxima_hora_dt.strftime("%I:00 %p").lstrip('0')
    
    recs = calcular_prediccion_kalshi(precio)
    
    embed = discord.Embed(
        title=f"⏳ PREPARACIÓN CIERRE DE VELA ({texto_proxima_hora})",
        description=f"Faltan **{minutos_restantes} minutos** para el cierre a las **{texto_proxima_hora}**.\nInversión: **$10 USD**",
        color=discord.Color.gold()
    )
    
    embed.add_field(name="Precio BTC Actual", value=f"**${precio:,.2f}**", inline=True)
    embed.add_field(name="📊 Pico Máximo de la Hora", value=f"${recs['pico_alto']:,.2f}", inline=True)
    embed.add_field(name="📊 Punto Mínimo de la Hora", value=f"${recs['pico_bajo']:,.2f}", inline=True)
    
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
        description=f"Precio BTC Actual: **${precio:,.2f}**\n*Rango Medio Reciente: ±${obtener_promedio_rango_horario():,.0f} USD*",
        color=discord.Color.purple()
    )
    
    techos = [f"• BTC **Arriba de ${base_100 + (100 * i):,.0f}**" for i in range(1, 4)]
    pisos = [f"• BTC **Debajo de ${base_100 - (100 * i):,.0f}**" for i in range(0, 3)]
    
    embed.add_field(name="📈 Contratos UP / YES", value="\n".join(techos), inline=False)
    embed.add_field(name="📉 Contratos DOWN / NO", value="\n".join(pisos), inline=False)

    await ctx.send(embed=embed)

@bot.command(name="memoria", aliases=["stats"])
async def ver_memoria(ctx):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT MIN(low_price), MAX(high_price), AVG(close_price), COUNT(*) FROM btc_hourly_candles")
    row = cursor.fetchone()
    conn.close()
    
    if not row or row[3] == 0:
        await ctx.send("🧠 Recopilando historial de velas horarias...")
        return
        
    embed = discord.Embed(title="🧠 MEMORIA DE VELAS HORARIAS (OHLC)", color=discord.Color.blue())
    embed.add_field(name="Mínimo Registrado", value=f"${row[0]:,.2f}", inline=True)
    embed.add_field(name="Máximo Registrado", value=f"${row[1]:,.2f}", inline=True)
    embed.add_field(name="Promedio Cierres", value=f"${row[2]:,.2f}", inline=False)
    embed.add_field(name="Velas de 1H Guardadas", value=f"{row[3]} horas", inline=True)
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

                    bloque_actual_1h = (timestamp_int + 2) // 3600

                    # ----------------------------------------------------
                    # ALERTA AUTOMÁTICA AL CAMBIAR LA HORA (:00 EXACTO)
                    # ----------------------------------------------------
                    if ultimo_bloque_1h != bloque_actual_1h:
                        ultimo_bloque_1h = bloque_actual_1h
                        
                        ahora_local = obtener_hora_local()
                        minutos_restantes = 60 - ahora_local.minute
                        timestamp_proxima = ahora_local.timestamp() + (minutos_restantes * 60)
                        proxima_hora_dt = datetime.fromtimestamp(timestamp_proxima, tz=ZONA_HORARIA_LOCAL)
                        texto_proxima_hora = proxima_hora_dt.strftime("%I:00 %p").lstrip('0')

                        recs = calcular_prediccion_kalshi(precio_btc)

                        embed = discord.Embed(
                            title=f"🚨 RECOMENDACIÓN DE ENTRADA KALSHI ($10 USD) - CIERRE {texto_proxima_hora}",
                            description=f"Precio Apertura de la Hora: **${precio_btc:,.2f}**\nOperación recomendada para cerrar a las **{texto_proxima_hora}**",
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
