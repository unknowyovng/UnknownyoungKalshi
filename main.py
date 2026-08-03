import os
import time
import asyncio
import sqlite3
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
# 2. BASE DE DATOS LOCAL (MEMORIA DE PRECIOS 30 DÍAS)
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
    
    # Limpiar datos más antiguos de 30 días (30 días * 24 horas * 3600 segundos)
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
        FROM btc_prices
        WHERE timestamp >= ?
    """, (hace_30_dias,))
    
    row = cursor.fetchone()
    conn.close()
    if row and row[3] > 0:
        return {"min": row[0], "max": row[1], "avg": row[2], "registros": row[3]}
    return None

init_db()

# ==========================================
# 3. CONFIGURACIÓN DE DISCORD Y ESTRATEGIA (1 HORA)
# ==========================================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

manual_target = None
modo_manual = False
target_kalshi_auto = None

# Parámetros Adaptados a Marcos de 1 HORA (BTC)
UMBRAL_BALLENA_BTC = 5.0  
MARGEN_MINIMO_CONFIRMACION = 15.0  # Mínimo +$15 sobre el target para confirmar UP en 1H
MARGEN_MAXIMO_ENTRADA = 60.0      # Máximo +$60 para no entrar sobrecomprado
CAIDA_DESDE_MAXIMO_ALERTA = 25.0  # Alerta de retroceso si cae $25 desde el pico de la hora
STOP_LOSS_ABS_CAIDA = 30.0        # Stop Loss si cae $30 bajo el Target

COOLDOWN_ENTRADAS = 20            
COOLDOWN_RETROCESO = 15           

# ==========================================
# 4. COMANDOS DE DISCORD (!target, !memoria, !stats)
# ==========================================
@bot.command(name="target")
async def set_target(ctx, valor: str = None):
    global manual_target, modo_manual

    if valor is None:
        if modo_manual and manual_target:
            estado = f"🎯 Target Manual Actual (1H): ${manual_target:,.2f}"
        elif target_kalshi_auto:
            estado = f"🤖 Target Kalshi Auto (1H): ${target_kalshi_auto:,.2f}"
        else:
            estado = "🤖 Modo 1H: AUTOMÁTICO (Obteniendo datos...)"
        await ctx.send(f"ℹ️ {estado}\nUsa `!target <precio>` o `!target auto` para cambiarlo.")
        return

    if valor.lower() in ["auto", "reset", "automatico"]:
        modo_manual = False
        manual_target = None
        await ctx.send("🤖 **Target 1H restablecido a MODO AUTOMÁTICO.**")
        print("🔄 Target cambiado a MODO AUTOMÁTICO (1H).")
    else:
        try:
            valor_limpio = valor.replace(",", "").replace("$", "")
            precio = float(valor_limpio)
            
            manual_target = precio
            modo_manual = True
            
            await ctx.send(f"🎯 **Target 1H fijado manualmente en:** `${manual_target:,.2f}`")
            print(f"📌 Target 1H fijado manualmente en: {manual_target}")
        except ValueError:
            await ctx.send("❌ **Error:** Formato incorrecto. Ejemplo: `!target 63469.33` ")

@bot.command(name="memoria")
@bot.command(name="stats")
async def ver_memoria(ctx):
    stats = obtener_estadisticas_mes()
    if not stats or stats["registros"] == 0:
        await ctx.send("🧠 **Memoria en construcción:** El bot está recopilando datos...")
        return

    embed = discord.Embed(
        title="🧠 MEMORIA DE PRECIOS BTC (ÚLTIMO MES)",
        color=discord.Color.blue()
    )
    embed.add_field(name="Mínimo Registrado (30d)", value=f"${stats['min']:,.2f}", inline=True)
    embed.add_field(name="Máximo Registrado (30d)", value=f"${stats['max']:,.2f}", inline=True)
    embed.add_field(name="Precio Promedio (30d)", value=f"${stats['avg']:,.2f}", inline=False)
    embed.add_field(name="Total Puntos Guardados", value=f"{stats['registros']:,} lecturas", inline=True)
    embed.set_footer(text="Datos guardados en base de datos persistente SQLite.")

    await ctx.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

# ==========================================
# 5. CONSULTAS DE API Y CARGA HISTÓRICA INICIAL
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

async def precargar_historial_30_dias(session):
    """Carga los datos de los últimos 30 días desde Coinbase API al iniciar"""
    print("⏳ Precargando memoria de 30 días desde Coinbase API...")
    url = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=3600"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with session.get(url, headers=headers, timeout=5) as resp:
            if resp.status == 200:
                candles = await resp.json()
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                for c in candles:
                    ts, low, high, open_p, close_p, vol = c[0], c[1], c[2], c[3], c[4], c[5]
                    cursor.execute("""
                        INSERT OR REPLACE INTO btc_prices (timestamp, price, high, low)
                        VALUES (?, ?, ?, ?)
                    """, (ts, close_p, high, low))
                conn.commit()
                conn.close()
                print("✅ Memoria del último mes sincronizada e inicializada correctamente.")
    except Exception as e:
        print(f"⚠️ Error al sincronizar historial de 30 días: {e}")

async def obtener_price_to_beat_kalshi_1h(session):
    url = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=3600"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with session.get(url, headers=headers, timeout=2) as resp:
            if resp.status == 200:
                candles = await resp.json()
                if candles:
                    candles_sorted = sorted(candles, key=lambda x: x[0], reverse=True)
                    return float(candles_sorted[0][3])
    except Exception as e:
        print(f"⚠️ Error al obtener Target 1H de Kalshi: {e}")
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
# 6. CICLO DE MONITOREO DE 1 HORA CON MEMORIA
# ==========================================
async def ciclo_monitoreo():
    await bot.wait_until_ready()
    global manual_target, modo_manual, target_kalshi_auto
    
    canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")
    ultimo_bloque_1h = None
    maximo_precio_bloque = 0.0

    ultimo_envio_entrada = 0
    ultimo_envio_retroceso = 0
    ultimo_envio_salida = 0

    async with aiohttp.ClientSession() as session:
        # Precargar memoria del mes al iniciar
        await precargar_historial_30_dias(session)

        while not bot.is_closed():
            try:
                if canal:
                    precio_btc = await obtener_precio_btc(session)

                    if precio_btc is not None:
                        tiempo_actual = time.time()
                        timestamp_int = int(tiempo_actual)

                        # Guardar precio actual en la memoria SQLite
                        guardar_precio_db(timestamp_int, precio_btc)

                        # ⏱️ ANTICIPACIÓN DE 2 SEGUNDOS EN MARCO DE 1 HORA (3600s)
                        timestamp_anticipado = timestamp_int + 2
                        bloque_actual_1h = timestamp_anticipado // 3600

                        # Detección de cambio de bloque de 1 HORA
                        if ultimo_bloque_1h != bloque_actual_1h or target_kalshi_auto is None:
                            target_kalshi_auto = precio_btc
                            
                            target_vela = await obtener_price_to_beat_kalshi_1h(session)
                            if target_vela:
                                target_kalshi_auto = target_vela

                            ultimo_bloque_1h = bloque_actual_1h
                            maximo_precio_bloque = precio_btc
                            
                            ultimo_envio_entrada = 0
                            ultimo_envio_retroceso = 0
                            ultimo_envio_salida = 0
                            print(f"⚡ [NUEVA HORA - 2s ANTICIPACIÓN] Target 1H: ${target_kalshi_auto:,.2f}")

                        target_activo = manual_target if modo_manual and manual_target else target_kalshi_auto

                        if target_activo:
                            if precio_btc > maximo_precio_bloque:
                                maximo_precio_bloque = precio_btc

                            diferencia = precio_btc - target_activo
                            print(f"🔍 [1H] BTC: ${precio_btc:,.2f} | Max Hora: ${maximo_precio_bloque:,.2f} | Target: ${target_activo:,.2f}")

                            # 1. SEÑAL DE ENTRADA EN 1 HORA
                            if MARGEN_MINIMO_CONFIRMACION <= diferencia <= MARGEN_MAXIMO_ENTRADA:
                                if (tiempo_actual - ultimo_envio_entrada) >= COOLDOWN_ENTRADAS:
                                    accion = "COMPRAR UP (1 HORA) 🚀"
                                    
                                    stats_mes = obtener_estadisticas_mes()
                                    contexto_text = ""
                                    if stats_mes:
                                        contexto_text = f"📊 Rango 30d: ${stats_mes['min']:,.0f} - ${stats_mes['max']:,.0f}"

                                    embed = discord.Embed(
                                        title="🚨 NUEVA SEÑAL KALSHI BTC (1H)",
                                        color=discord.Color.green()
                                    )
                                    embed.add_field(name="Acción", value=f"🔥 **{accion}**", inline=False)
                                    embed.add_field(name="Precio BTC (Coinbase)", value=f"${precio_btc:,.2f}", inline=True)
                                    embed.add_field(name="Target 1H a Vencer", value=f"${target_activo:,.2f}", inline=True)
                                    embed.add_field(name="Margen A Favor", value=f"+${diferencia:,.2f}", inline=False)
                                    if contexto_text:
                                        embed.set_footer(text=contexto_text)

                                    await canal.send(embed=embed)
                                    print(f"⚡ [SEÑAL ENTRADA 1H] {accion} | BTC: ${precio_btc:,.2f}")
                                    ultimo_envio_entrada = tiempo_actual

                            # 2. ALERTA DE RETROCESO EN 1 HORA
                            caida_desde_pico = maximo_precio_bloque - precio_btc
                            if caida_desde_pico >= CAIDA_DESDE_MAXIMO_ALERTA and precio_btc > target_activo:
                                if (tiempo_actual - ultimo_envio_retroceso) >= COOLDOWN_RETROCESO:
                                    embed = discord.Embed(
                                        title="⚠️ ALERTA DE RETROCESO (1 HORA)",
                                        color=discord.Color.gold()
                                    )
                                    embed.add_field(name="Aviso", value="📉 **El precio cayó $25+ desde el pico de la hora.**", inline=False)
                                    embed.add_field(name="Máximo de la Hora", value=f"${maximo_precio_bloque:,.2f}", inline=True)
                                    embed.add_field(name="Precio Actual", value=f"${precio_btc:,.2f}", inline=True)
                                    embed.add_field(name="Retroceso Detectado", value=f"-${caida_desde_pico:,.2f}", inline=False)

                                    await canal.send(embed=embed)
                                    print(f"⚠️ [RETROCESO 1H] Caída de -${caida_desde_pico:,.2f} desde pico.")
                                    ultimo_envio_retroceso = tiempo_actual

                            # 3. STOP LOSS DEFINITIVO EN 1H
                            elif precio_btc < (target_activo - STOP_LOSS_ABS_CAIDA):
                                if (tiempo_actual - ultimo_envio_salida) >= 30:
                                    accion = "SALIR / CERRAR POSICIÓN 🛑"
                                    caida = target_activo - precio_btc
                                    embed = discord.Embed(
                                        title="🛑 STOP LOSS (1 HORA)",
                                        color=discord.Color.red()
                                    )
                                    embed.add_field(name="Acción", value=f"🚨 **{accion}**", inline=False)
                                    embed.add_field(name="Precio BTC Actual", value=f"${precio_btc:,.2f}", inline=True)
                                    embed.add_field(name="Target de Entrada", value=f"${target_activo:,.2f}", inline=True)
                                    embed.add_field(name="Pérdida", value=f"-${caida:,.2f}", inline=False)

                                    await canal.send(embed=embed)
                                    print(f"🛑 [STOP LOSS 1H] Salida enviada a Discord.")
                                    ultimo_envio_salida = tiempo_actual

                    # Monitoreo de ballenas
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
                print(f"⚠️ Error en ciclo de monitoreo 1H: {e}")

            await asyncio.sleep(1)

# ==========================================
# 7. INICIALIZACIÓN
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot (1H + Memoria 30 Días) conectado como: {bot.user.name}")
    bot.loop.create_task(ciclo_monitoreo())

async def main():
    async with bot:
        token = os.environ.get("DISCORD_BOT_TOKEN")
        if not token:
            raise ValueError("❌ Falta la variable DISCORD_BOT_TOKEN en Render.")
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
