import os
import asyncio
import discord
from discord.ext import commands

# ==========================================
# 1. CONFIGURACIÓN DE INTENTS DE DISCORD
# ==========================================
intents = discord.Intents.default()
# Requisito obligatorio para leer mensajes como '!target'
intents.message_content = True  

bot = commands.Bot(command_prefix="!", intents=intents)

# Variables globales para el manejo del Target
manual_target = None  # Almacena el target fijado manualmente por comando
modo_manual = False   # Indica si está activo el modo manual

# ==========================================
# 2. EVENTOS DEL BOT
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado exitosamente como: {bot.user.name}")
    print("🤖 Esperando comandos en el chat...")

@bot.event
async def on_message(message):
    # Evitar que el bot responda a sus propios mensajes
    if message.author == bot.user:
        return

    # Imprimir en consola para depuración de mensajes recibidos
    if message.content.startswith("!"):
        print(f"📩 Comando detectado de {message.author}: {message.content}")

    # CRUCIAL: Permite que los comandos (@bot.command) se procesen si hay un evento on_message
    await bot.process_commands(message)

# ==========================================
# 3. COMANDOS DE DISCORD
# ==========================================
@bot.command(name="target")
async def set_target(ctx, valor: str = None):
    global manual_target, modo_manual

    if valor is None:
        estado = f"🎯 Target actual: ${manual_target:.2f}" if modo_manual else "🤖 Modo: AUTOMÁTICO (15m)"
        await ctx.send(f"ℹ️ {estado}\nUsa `!target <precio>` o `!target auto` para cambiarlo.")
        return

    if valor.lower() in ["auto", "reset", "automatico"]:
        modo_manual = False
        manual_target = None
        await ctx.send("🤖 **Target restablecido a MODO AUTOMÁTICO (15m).**")
        print("🔄 Target cambiado a MODO AUTOMÁTICO.")
    else:
        try:
            # Limpiar comas o signos por si se ingresan de más
            valor_limpio = valor.replace(",", "").replace("$", "")
            precio = float(valor_limpio)
            
            manual_target = precio
            modo_manual = True
            
            await ctx.send(f"🎯 **Target fijado manualmente en:** `${manual_target:.2f}`")
            print(f"📌 Target fijado manualmente en: {manual_target}")
        except ValueError:
            await ctx.send("❌ **Error:** Por favor ingresa un número válido. Ejemplo: `!target 63470.00`")

# ==========================================
# 4. LÓGICA DE OBTENCIÓN DEL TARGET
# ==========================================
def obtener_target_actual(target_calculado_auto):
    """
    Retorna el target manual si está activo, 
    o el target calculado automáticamente por el script.
    """
    global manual_target, modo_manual
    
    if modo_manual and manual_target is not None:
        return manual_target
    return target_calculado_auto

# ==========================================
# 5. BUCLE PRINCIPAL / MONITOREO (EJEMPLO)
# ==========================================
async def ciclo_monitoreo():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            # 1. Obtener precio actual de BTC y calcular target automático
            # (Reemplaza con tu función real de obtención de datos)
            precio_btc = 63468.01 
            target_auto = 63456.97 

            # 2. Determinar qué target usar (Manual o Auto)
            target_a_vencer = obtener_target_actual(target_auto)

            # 3. Tu lógica de señales...
            # print(f"Analizando... Precio: {precio_btc} | Target Activo: {target_a_vencer}")

        except Exception as e:
            print(f"⚠️ Error en ciclo de monitoreo: {e}")
            
        await asyncio.sleep(15)  # Revisa cada 15 segundos

# ==========================================
# 6. INICIALIZACIÓN
# ==========================================
async def main():
    async with bot:
        # Iniciar la tarea en segundo plano junto con el bot
        bot.loop.create_task(ciclo_monitoreo())
        
        # Cargar token de la variable de entorno de Render
        token = os.environ.get("DISCORD_BOT_TOKEN")
        if not token:
            raise ValueError("❌ No se encontró la variable DISCORD_BOT_TOKEN en el entorno.")
            
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
