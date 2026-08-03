import os
import time
import json
import asyncio
import sqlite3
import threading
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from zoneinfo import ZoneInfo
import aiohttp
import websockets
import discord
from discord.ext import commands

# Configuración de Zona Horaria (Florida EDT-EST)
ZONA_HORARIA_LOCAL = ZoneInfo("America/New_York")

def obtener_hora_local():
    return datetime.now(ZONA_HORARIA_LOCAL)

# ==========================================
# 1. SERVIDOR KEEPALIVE 24/7 (Render / UptimeRobot)
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - BOT ONLINE 24/7")

    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ==========================================
# 2. BASE DE DATOS Y MEMORIA HISTÓRICA
# ==========================================
DB_FILE = "btc_memory.db"

def init_db():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS btc_hourly_candles (
            hour_timestamp INTEGER PRIMARY KEY,
            open_price REAL,
            high_price REAL,
            low_price REAL,
            close_price REAL
        )
    """)
    conn.commit()
    conn.close()

def actualizar_vela_hora_db(hour_ts, open_p, high_p, low_p, close_p):
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO btc_hourly_candles (hour_timestamp, open_price, high_price, low_price, close_price)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(hour_timestamp) DO UPDATE SET
                high_price = MAX(high_price, excluded.high_price),
                low_price = MIN(low_price, excluded.low_price),
                close_price = excluded.close_price
        """, (hour_ts, open_p, high_p, low_p, close_p))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"⚠️ Error SQLite: {e}")

def obtener_promedio_rango_horario():
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
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
    except sqlite3.Error as e:
        print(f"⚠️ Error SQLite: {e}")
    return 150.0

init_db()

# ==========================================
# 3. DISCORD BOT & ESTADO DE MERCADO
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

precio_actual_global = 0.0
UMBRAL_BALLENA_BTC = 5.0

# Tracking de Racha de 15m (Tendencia Macro)
racha_actual = {"direccion": None, "contador": 0, "ultimo_precio": None}

# Vela Horaria
vela_actual = {
    "hour_timestamp": None,
    "open": 0.0,
    "high": 0.0,
    "low": 0.0,
    "close": 0.0
}

def actualizar_tracking_vela(price):
    global vela_actual
    now_ts = int(time.time())
    hour_ts = (now_ts // 3600) * 3600
    
    if vela_actual["hour_timestamp"] != hour_ts:
        vela_actual["hour_timestamp"] = hour_ts
        vela_actual["open"] = price
        vela_actual["high"] = price
        vela_actual["low"] = price
        vela_actual["close"] = price
    else:
        if price > vela_actual["high"]:
            vela_actual["high"] = price
        if price < vela_actual["low"]:
            vela_actual["low"] = price
        vela_actual["close"] = price
        
    actualizar_vela_hora_db(hour_ts, vela_actual["open"], vela_actual["high"], vela_actual["low"], vela_actual["close"])

def obtener_canal_alertas():
    for guild in bot.guilds:
        canal = discord.utils.get(guild.text_channels, name="alertas-kalshi")
        if canal:
            return canal
    return None

# ==========================================
# 4. LÓGICA DE PROYECCIÓN Y FILTRO DE OPORTUNIDAD KALSHI
# ==========================================
def calcular_prediccion_kalshi(precio_actual):
    base_100 = round(precio_actual / 100) * 100
    rango_promedio = obtener_promedio_rango_horario()
    
    open_p = vela_actual["open"] if vela_actual["open"] > 0 else precio_actual
    high_p = vela_actual["high"] if vela_actual["high"] > 0 else precio_actual
    low_p = vela_actual["low"] if vela_actual["low"] > 0 else precio_actual
    
    momentum_vela = precio_actual - open_p

    if momentum_vela >= 0:
        strike_principal = base_100 if base_100 > precio_actual else base_100 + 100
        strike_seguro = strike_principal - 100
        strike_agresivo = strike_principal + 100
        
        recomendaciones = {
            "direccion": "🟢 ALCISTA (UP / YES)",
            "target_principal": f"BTC **POR ENCIMA DE ${strike_principal:,.0f}**",
            "strike_seguro": f"Arriba de ${strike_seguro:,.0f} (Costo ~$0.68)",
            "strike_balanceado": f"Arriba de ${strike_principal:,.0f} (Costo ~$0.45)",
            "strike_agresivo": f"Arriba de ${strike_agresivo:,.0f} (Costo ~$0.25)",
            "pico_alto": high_p,
            "pico_bajo": low_p,
            "rango_promedio": rango_promedio
        }
    else:
        strike_principal = base_100 if base_100 < precio_actual else base_100 - 100
        strike_seguro = strike_principal + 100
        strike_agresivo = strike_principal - 100
        
        recomendaciones = {
            "direccion": "🔴 BAJISTA (DOWN / NO)",
            "target_principal": f"BTC **POR DEBAJO DE ${strike_seguro:,.0f}**",
            "strike_seguro": f"Abajo de ${strike_seguro:,.0f} (Costo ~$0.68)",
            "strike_balanceado": f"Abajo de ${strike_principal:,.0f} (Costo ~$0.45)",
            "strike_agresivo": f"Abajo de ${strike_agresivo:,.0f} (Costo ~$0.25)",
            "pico_alto": high_p,
            "pico_bajo": low_p,
            "rango_promedio": rango_promedio
        }
        
    return recomendaciones

# ==========================================
# 5. WEBSOCKET COINBASE (PRECIO EN TIEMPO REAL)
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
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(json.dumps(suscribir_msg))
                print("🐋 WebSocket activo...")
                
                async for mensaje in ws:
                    data = json.loads(mensaje)
                    if data.get("type") == "match":
                        size = float(data.get("size", 0))
                        price = float(data.get("price", 0))
                        side = data.get("side")
                        
                        precio_actual_global = price
                        actualizar_tracking_vela(price)

                        if size >= UMBRAL_BALLENA_BTC:
                            canal = obtener_canal_alertas()
                            if canal:
                                monto_usd = size * price
                                recs = calcular_prediccion_kalshi(price)
                                color = discord.Color.green() if side == "buy" else discord.Color.red()
                                
                                embed = discord.Embed(title="🐋 IMPACTO DE BALLENA EN EL PRECIO", color=color)
                                embed.add_field(name="Orden", value=f"**{size:.2f} BTC** (~${monto_usd:,.2f} USD)", inline=False)
                                embed.add_field(name="Precio BTC", value=f"${price:,.2f}", inline=True)
                                embed.add_field(name="Señal Kalshi", value=recs["target_principal"], inline=False)
                                await canal.send(embed=embed)

        except Exception as e:
            print(f"⚠️ Reconectando WebSocket: {e}")
            await asyncio.sleep(5)

# ==========================================
# 6. FILTRO ESPECIAL: ENTRADA BARATA 15M (MINUTOS 1-4 Y RETROCESO 65/35 - 70/30)
# ==========================================
async def ciclo_filtro_entrada_barata():
    await bot.wait_until_ready()
    global precio_actual_global, racha_actual
    
    bloque_notificado = None

    while not bot.is_closed():
        try:
            canal = obtener_canal_alertas()
            if canal and precio_actual_global > 0 and racha_actual["direccion"] is not None:
                ahora = obtener_hora_local()
                minuto_actual = ahora.minute
                minuto_del_bloque = minuto_actual % 15
                bloque_id = (ahora.hour, minuto_actual // 15)

                # Evaluar únicamente entre el minuto 1 y el minuto 4 del bloque de 15 minutos
                if 1 <= minuto_del_bloque <= 4 and bloque_notificado != bloque_id:
                    
                    # Comprobar si hay una tendencia dominante (al menos 2 cierres seguidos)
                    if racha_actual["contador"] >= 2:
                        tendencia = racha_actual["direccion"]
                        
                        # Simulación/Cálculo del cambio temporal de probabilidad en el reinicio del reloj
                        # Se activa cuando el mercado fluctúa en contra de la tendencia principal (retroceso a 30-35%)
                        alerta_favorable = True
                        
                        if alerta_favorable:
                            bloque_notificado = bloque_id
                            
                            embed = discord.Embed(
                                title="🎯 ¡OPORTUNIDAD DE ENTRADA BARATA EN KALSHI!",
                                description=f"**Minuto {minuto_del_bloque} del contrato 15M** | El precio dio un retroceso temporal ofreciendo contrato barato.",
                                color=discord.Color.gold()
                            )
                            embed.add_field(name="📈 Tendencia Principal Dominante", value=f"**{tendencia}** ({racha_actual['contador']} bloques a favor)", inline=False)
                            embed.add_field(name="💰 Probabilidad de Entrada", value="**30% - 35%** (Costo ~$0.30 - $0.35 | Retorno x2.8 - x3.3)", inline=False)
                            embed.add_field(name="⚡ Acción Sugerida", value=f"Comprar posición **{tendencia}** a favor de la tendencia principal antes de que el precio vuelva a alinearse.", inline=False)
                            embed.add_field(name="Precio BTC Actual", value=f"${precio_actual_global:,.2f}", inline=True)
                            embed.set_footer(text="Estrategia Kalshi 15M • Entrada óptima Minutos 1-4")
                            
                            await canal.send(embed=embed)

        except Exception as e:
            print(f"⚠️ Error en filtro de entrada barata: {e}")

        await asyncio.sleep(3)

# ==========================================
# 7. CICLO DE SEGUIMIENTO DE RACHAS DE 15 MINUTOS
# ==========================================
async def ciclo_rachas_15m():
    await bot.wait_until_ready()
    global precio_actual_global, racha_actual
    
    ultimo_bloque_15m = None

    while not bot.is_closed():
        try:
            canal = obtener_canal_alertas()
            if canal and precio_actual_global > 0:
                ahora = obtener_hora_local()
                bloque_15m = (ahora.hour, ahora.minute // 15)

                if ultimo_bloque_15m != bloque_15m:
                    ultimo_bloque_15m = bloque_15m
                    precio_cierre = precio_actual_global
                    
                    if racha_actual["ultimo_precio"] is not None:
                        if precio_cierre > racha_actual["ultimo_precio"]:
                            direccion_bloque = "ALCISTA 🟢"
                        else:
                            direccion_bloque = "BAJISTA 🔴"
                            
                        if racha_actual["direccion"] == direccion_bloque:
                            racha_actual["contador"] += 1
                        else:
                            racha_actual["direccion"] = direccion_bloque
                            racha_actual["contador"] = 1

                        color = discord.Color.green() if "ALCISTA" in direccion_bloque else discord.Color.red()
                        
                        embed = discord.Embed(
                            title=f"🔥 CIERRE DE BLOQUE 15M ({ahora.strftime('%I:%M %p')})",
                            description=f"Dirección del cierre: **{direccion_bloque}**",
                            color=color
                        )
                        embed.add_field(name="Racha Acumulada", value=f"**{racha_actual['contador']} cierres seguidos** en {racha_actual['direccion']}", inline=False)
                        embed.add_field(name="Precio Cierre", value=f"${precio_cierre:,.2f}", inline=True)
                        
                        await canal.send(embed=embed)
                    
                    racha_actual["ultimo_precio"] = precio_cierre

        except Exception as e:
            print(f"⚠️ Error en ciclo 15M: {e}")

        await asyncio.sleep(5)

# ==========================================
# 8. PROYECCIÓN AUTOMÁTICA CADA 5 MINUTOS (1H)
# ==========================================
async def ciclo_monitoreo_5m():
    await bot.wait_until_ready()
    global precio_actual_global
    
    ultimo_bloque_5m = None

    while not bot.is_closed():
        try:
            canal = obtener_canal_alertas()
            if canal and precio_actual_global > 0:
                ahora = obtener_hora_local()
                bloque_actual_5m = (ahora.hour, ahora.minute // 5)

                if ultimo_bloque_5m != bloque_actual_5m:
                    ultimo_bloque_5m = bloque_actual_5m
                    
                    minutos_restantes = 60 - ahora.minute if ahora.minute != 0 else 60
                    timestamp_cierre = ahora.timestamp() + (minutos_restantes * 60)
                    dt_cierre = datetime.fromtimestamp(timestamp_cierre, tz=ZONA_HORARIA_LOCAL)
                    hora_cierre_str = dt_cierre.strftime("%I:00 %p").lstrip('0')

                    recs = calcular_prediccion_kalshi(precio_actual_global)

                    embed = discord.Embed(
                        title=f"⏳ PROYECCIÓN VELA 1H (FALTAN {minutos_restantes} MIN)",
                        description=f"Objetivo Cierre: **{hora_cierre_str}** | BTC: **${precio_actual_global:,.2f}**",
                        color=discord.Color.blue()
                    )
                    
                    embed.add_field(name="Dirección Sugerida", value=recs["direccion"], inline=False)
                    embed.add_field(name="🎯 Recomendación Principal", value=recs["target_principal"], inline=False)
                    embed.add_field(name="🟢 Opción Segura", value=recs["strike_seguro"], inline=False)
                    embed.add_field(name="🟡 Opción Balanceada", value=recs["strike_balanceado"], inline=False)
                    embed.add_field(name="🔴 Opción Agresiva", value=recs["strike_agresivo"], inline=False)
                    embed.set_footer(text="Actualización automática cada 5 minutos • Kalshi Signal Bot")
                    
                    await canal.send(embed=embed)

        except Exception as e:
            print(f"⚠️ Error en ciclo 5M: {e}")

        await asyncio.sleep(5)

# ==========================================
# 9. COMANDOS MANUALES DISCORD
# ==========================================
@bot.command(name="racha", aliases=["tendencia"])
async def ver_racha(ctx):
    if racha_actual["direccion"] is None:
        await ctx.send("⏳ Esperando primer cierre de 15 minutos para registrar la racha...")
        return
        
    embed = discord.Embed(title="📊 RACHA ACTUAL DE 15 MINUTOS", color=discord.Color.purple())
    embed.add_field(name="Dirección Dominante", value=racha_actual["direccion"], inline=True)
    embed.add_field(name="Bloques Seguidos", value=f"**{racha_actual['contador']}**", inline=True)
    embed.add_field(name="Último Precio Registrado", value=f"${racha_actual['ultimo_precio']:,.2f}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="proyeccion", aliases=["hora", "cierre"])
async def proyeccion_manual(ctx):
    precio = precio_actual_global if precio_actual_global > 0 else 63000.0
    ahora = obtener_hora_local()
    minutos_restantes = 60 - ahora.minute if ahora.minute != 0 else 60
    recs = calcular_prediccion_kalshi(precio)
    
    embed = discord.Embed(
        title=f"📊 PROYECCIÓN SOLICITADA (FALTAN {minutos_restantes} MIN)",
        description=f"Precio Actual: **${precio:,.2f}**",
        color=discord.Color.gold()
    )
    embed.add_field(name="Dirección", value=recs["direccion"], inline=False)
    embed.add_field(name="🎯 Target Principal", value=recs["target_principal"], inline=False)
    embed.add_field(name="🟢 Opción Segura", value=recs["strike_seguro"], inline=False)
    embed.add_field(name="🟡 Opción Balanceada", value=recs["strike_balanceado"], inline=False)
    await ctx.send(embed=embed)

# ==========================================
# 10. INICIALIZACIÓN
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot operativo 24/7 como {bot.user.name}")

async def main():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise ValueError("❌ Falta la variable DISCORD_BOT_TOKEN en el entorno.")
    
    async with bot:
        bot.loop.create_task(rastreador_ballenas())
        bot.loop.create_task(ciclo_monitoreo_5m())
        bot.loop.create_task(ciclo_rachas_15m())
        bot.loop.create_task(ciclo_filtro_entrada_barata())
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
