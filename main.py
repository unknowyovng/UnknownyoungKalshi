import os
import time
import requests
import asyncio

# ==========================================
# CONFIGURACIÓN DE VARIABLES DE ENTORNO
# ==========================================
# Reemplaza la URL de abajo con la URL de tu Webhook de Discord
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "TU_DISCORD_WEBHOOK_URL_AQUI")

# Claves de API para monitoreo de portfolio / exchanges (opcional)
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY", "")
EXCHANGE_API_SECRET = os.getenv("EXCHANGE_API_SECRET", "")

# ==========================================
# MÓDULO DE ALERTAS DISCORD
# ==========================================
def send_discord_alert(title: str, description: str, color: int = 3447003):
    """Envía un mensaje embebido al canal de Discord configurado."""
    if DISCORD_WEBHOOK_URL == "TU_DISCORD_WEBHOOK_URL_AQUI" or not DISCORD_WEBHOOK_URL:
        print("[ADVERTENCIA] Configura la variable DISCORD_WEBHOOK_URL.")
        return

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    
    payload = {"embeds": [embed]}
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code != 204:
            print(f"[ERROR DISCORD] Status Code: {response.status_code}")
    except Exception as e:
        print(f"[EXCEPCIÓN DISCORD] Error al enviar alerta: {e}")

# ==========================================
# MÓDULO DE MONITOREO DE LATENCIA
# ==========================================
def check_latency(target_url: str = "https://api.coinbase.com/v2/time", threshold_ms: float = 500.0):
    """Mide el tiempo de respuesta del servidor objetivo y alerta si hay retraso."""
    start_time = time.time()
    try:
        response = requests.get(target_url, timeout=3)
        latency_ms = (time.time() - start_time) * 1000
        
        print(f"[LATENCIA] {target_url}: {latency_ms:.2f} ms")
        
        if latency_ms > threshold_ms:
            send_discord_alert(
                title="⚠️ Alerta de Latencia Elevada",
                description=f"Se detectó un retraso de **{latency_ms:.2f} ms** al conectar con `{target_url}`.",
                color=15158332 # Rojo
            )
        return latency_ms
    except Exception as e:
        send_discord_alert(
            title="🚨 Error de Conexión",
            description=f"Fallo de conexión con `{target_url}`: {str(e)}",
            color=15158332
        )
        return None

# ==========================================
# MÓDULO DE MONITOREO DE BALANCE / PORTFOLIO
# ==========================================
def check_portfolio_status():
    """Consulta el estado del balance y genera un reporte."""
    # Estructura base para conectar con tus APIs de Trading o Coinbase
    if not EXCHANGE_API_KEY or not EXCHANGE_API_SECRET:
        print("[INFO] API Keys no configuradas. Generando reporte simulado de balance.")
        # Ejemplo/Simulación:
        total_balance_usd = 12500.50
        daily_pnl = +3.45
    else:
        # Aquí va la integración real con la API usando EXCHANGE_API_KEY y SECRET
        total_balance_usd = 0.0
        daily_pnl = 0.0

    msg = (
        f"**Balance Total:** `${total_balance_usd:,.2f} USD`\n"
        f"**Rendimiento (24h):** `{daily_pnl:+.2f}%`"
    )
    
    send_discord_alert(
        title="📊 Reporte de Rendimiento y Portafolio",
        description=msg,
        color=3066993 # Verde
    )

# ==========================================
# BUCLE PRINCIPAL (MAIN LOOP)
# ==========================================
async def main_loop():
    send_discord_alert(
        title="🤖 Bot Captain Hook Activado",
        description="Sistema de monitoreo de noticias, latencia y balance iniciado correctamente.",
        color=3447003
    )
    
    while True:
        # 1. Chequeo de Latencia
        check_latency()
        
        # 2. Chequeo de Portfolio
        check_portfolio_status()
        
        # Espera de 15 minutos para la siguiente ejecución
        await asyncio.sleep(900)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\n[BOT] Detenido por el usuario.")
