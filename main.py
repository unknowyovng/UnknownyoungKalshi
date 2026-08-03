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

# Configuración de Zona Horaria (Hora del Este / Florida EDT-EST)
ZONA_HORARIA_LOCAL = ZoneInfo("America/New_York")

def obtener_hora_local():
    return datetime.now(ZONA_HORARIA_LOCAL)

# ==========================================
# 1. SERVIDOR WEB KEEPALIVE (Para UptimeRobot / Render 24/7)
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - BOT ONLINE 24/7")

    def log_message(self, format, *args):
        return  # Ocultar logs HTTP para no saturar la consola

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
    conn = sqlite3.connect(DB_FILE)
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
    conn.commit()
    conn.close()

def obtener_promedio_rango_horario():
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
    return 150.0

init_db()

# ==========================================
# 3. DISCORD BOT & ESTADO EN TIEMPO REAL
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

precio_actual_global = 0.0
UMBRAL_BALLENA_BTC = 5.0

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

# ==========================================
# 4. CÁLCULO DE PROYECCIÓN Y STRIKES KALSHI
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
            "strike_seguro": f"Arriba de ${strike_seguro:,.0f} (Costo ~$0.68) ➔ Retorno seguro",
            "strike_balanceado": f"Arriba de ${strike_principal:,.0f} (Costo ~$0.45) ➔ Balance óptimo",
            "strike_agresivo": f"Arriba de ${strike_agresivo:,.0f} (Costo ~$0.25) ➔ Alto retorno",
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
            "strike_seguro": f"Abajo de ${strike_seguro:,.0f} (Costo ~$0.68) ➔ Retorno seguro",
            "strike_balanceado": f"Abajo de ${strike_principal:,.0f} (Costo ~$0.45) ➔ Balance óptimo",
            "strike_agresivo": f"Abajo de ${strike_agresivo:,.0f} (Costo ~$0.25) ➔ Alto retorno",
            "pico_alto": high_p,
            "pico_bajo": low_p,
            "rango_promedio": rango_promedio
        }
        
    return recomendaciones

# ==========================================
# 5. WEBSOCKET DE BALLENAS EN TIEMPO REAL
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
                print("🐋 Rastreando mercado y ballenas 24/7...")
                
                async for mensaje in ws:
                    data = json.loads(mensaje)
                    if data.get("type") == "match":
                        size = float(data.get("size", 0))
                        price = float(data.get("price", 0))
                        side = data.get("side")
                        
                        precio_actual_global = price
                        actualizar_tracking_vela(price)

                        if size >= UMBRAL_BALLENA_BTC:
                            canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")
                            if canal:
                                monto_usd = size * price
                                recs = calcular_prediccion_kalshi(price)
                                color = discord.Color.green() if side == "buy" else discord.Color.red()
                                
                                embed = discord.Embed(title="🐋 ALERTA INSTANTÁNEA DE BALLENA", color=color)
                                embed.add_field(name="Volumen Detectado", value=f"**{size:.2f} BTC** (~${monto_usd:,.2f} USD)", inline=False)
                                embed.add_field(name="Precio BTC", value=f"${price:,.2f}", inline=True)
                                embed.add_field(name="Señal Kalshi", value=recs["target_principal"], inline=False)
                                embed.add_field(name="Opción Balanceada", value=recs["strike_balanceado"], inline=False)
                                
                                await canal.send(embed=embed)

        except Exception as e:
            print(f"⚠️ Reconectando WebSocket... ({e})")
            await asyncio.sleep(5)

# ==========================================
# 6. ALERTAS AUTOMÁTICAS CADA 5 MINUTOS
# ==========================================
async def ciclo_monitoreo_5m():
    await bot.wait_until_ready()
    global precio_actual_global
    
    canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")
    ultimo_bloque = None

    while not bot.is_closed():
        try:
            if canal and precio_actual_global > 0:
                ahora = obtener_hora_local()
                bloque_actual = (ahora.hour, ahora.minute // 5)

                if ultimo_bloque != bloque_actual:
                    ultimo_bloque = bloque_actual
                    
                    minutos_restantes = 60 - ahora.minute if ahora.minute != 0 else 60
                    timestamp_cierre = ahora.timestamp() + (minutos_restantes * 60)
                    dt_cierre = datetime.fromtimestamp(timestamp_cierre, tz=ZONA_HORARIA_LOCAL)
                    hora_cierre_str = dt_cierre.strftime("%I:00 %p").lstrip('0')

                    recs = calcular_prediccion_kalshi(precio_actual_global)

                    embed = discord.Embed(
                        title=f"⏳ PROYECCIÓN VELA 1H (FALTAN {minutos_restantes} MIN)",
                        description=f"Objetivo Cierre: **{hora_cierre_str}** | Precio BTC: **${precio_actual_global:,.2f}**",
                        color=discord.Color.blue()
                    )
                    
                    embed.add_field(name="Dirección Sugerida", value=recs["direccion"], inline=False)
                    embed.add_field(name="🎯 Recomendación Principal", value=recs["target_principal"], inline=False)
                    embed.add_field(name="🟢 Opción Segura", value=recs["strike_seguro"], inline=False)
                    embed.add_field(name="🟡 Opción Balanceada", value=recs["strike_balanceado"], inline=False)
                    embed.add_field(name="🔴 Opción Agresiva", value=recs["strike_agresivo"], inline=False)
                    embed.set_footer(text="Actualización automática cada 5 minutos • Kalshi Signal Bot 24/7")
                    
                    await canal.send(embed=embed)

        except Exception as e:
            print(f"⚠️ Error en ciclo 5M: {e}")

        await asyncio.sleep(3)

# ==========================================
# 7. COMANDOS MANUALES
# ==========================================
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

@bot.event
async def on_ready():
    print(f"✅ Bot listo y operativo como {bot.user.name}")
    bot.loop.create_task(rastreador_ballenas())
    bot.loop.create_task(ciclo_monitoreo_5m())

async def main():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise ValueError("❌ Falta la variable DISCORD_BOT_TOKEN en Render.")
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
