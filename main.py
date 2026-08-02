import os
import time
import requests
from datetime import datetime, timezone

# ==========================================
# CONFIGURACIÓN Y VARIABLES DE ENTORNO
# ==========================================
# Puedes pegar directamente tu URL entre las comillas si no usas variables en Render
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "PEGA_AQUI_TU_WEBHOOK_DE_DISCORD")

DISTANCIA_MAXIMA_TARGET = 15.0  # Máxima distancia en USD permitida para entrar
POLL_INTERVAL = 10              # Frecuencia de chequeo en segundos (10s)

# Estado global del bot
last_sent_action = "NEUTRAL"

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================
def send_discord_alert(message):
    """Envía un mensaje o alerta al webhook de Discord."""
    if not DISCORD_WEBHOOK_URL or "PEGA_AQUI" in DISCORD_WEBHOOK_URL:
        print("[DISCORD] Error: Webhook URL no configurada.")
        return

    payload = {"content": message}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        print(f"[DISCORD HTTP STATUS]: {response.status_code}")
    except Exception as e:
        print(f"[DISCORD ERROR]: No se pudo enviar el mensaje: {e}")

def get_btc_price():
    """Obtiene el precio actual de BTC desde la API de Coinbase con timeout."""
    try:
        url = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
        res = requests.get(url, timeout=5)
        data = res.json()
        return float(data["data"]["amount"])
    except Exception as e:
        print(f"[PRECIO ERROR]: Error consultando la API: {e}")
        return None

def get_kalshi_target_price():
    """
    Sustituye esta función si obtienes el Target directamente de la API de Kalshi.
    Por defecto devuelve None si no está integrado aún.
    """
    return None 

# ==========================================
# EVALUACIÓN DE SEÑALES Y REGLAS DE NEGOCIO
# ==========================================
def evaluate_market(current_price, target_price, current_minute):
    """
    Calcula la acción sugerida basándose en el precio, el objetivo y el tiempo de la vela (15m).
    """
    # 1. Filtro de seguridad para minutos finales (Cooldown en minutos 13 y 14)
    if current_minute >= 13:
        return "NEUTRAL", "Final de bloque (Cuota baja / Cooldown)"

    # 2. Si no hay Target configurado en la API, retornamos estado de espera
    if target_price is None:
        return "NEUTRAL", "Esperando confirmación / Target no configurado"

    distancia = target_price - current_price

    # 3. Filtro de Distancia Mínima al Target
    if distancia > DISTANCIA_MAXIMA_TARGET and current_minute > 3:
        return "NEUTRAL", f"Distancia al Target muy alta (${distancia:.2f})"

    # 4. Condición de Entrada UP
    if current_price >= (target_price - 5.0):
        return "COMPRAR UP", f"Impulso continuo (min {current_minute}/15)"
    
    # 5. Condición de Entrada DOWN
    elif current_price <= (target_price - DISTANCIA_MAXIMA_TARGET):
        return "COMPRAR DOWN", f"Tendencia bajista (min {current_minute}/15)"

    return "NEUTRAL", "Mercado lateral / Sin volumen suficiente"

# ==========================================
# BUCLE PRINCIPAL (MAIN LOOP)
# ==========================================
def main():
    global last_sent_action
    
    print("🚀 Bot Kalshi 15m iniciado con éxito.")
    send_discord_alert("🟢 **BOT CONECTADO**\nBot iniciado correctamente y monitoreando mercado.")

    while True:
        try:
            # Uso de timezone UTC moderno para evitar DeprecationWarning
            now = datetime.now(timezone.utc)
            current_minute = now.minute % 15  # Minuto relativo dentro de la vela de 15m
            
            btc_price = get_btc_price()
            target_price = get_kalshi_target_price()

            if btc_price is not None:
                current_action, detail = evaluate_market(btc_price, target_price, current_minute)

                # Log en consola de Render
                print(f"[{now.strftime('%H:%M:%S')}] BTC: ${btc_price:.2f} | ACCIÓN: {current_action} ({detail})")

                # ----------------------------------------------------
                # LÓGICA DE ALERTAS A DISCORD
                # ----------------------------------------------------
                
                # A) NUEVA ENTRADA O CAMBIO DE TENDENCIA
                if current_action in ["COMPRAR UP", "COMPRAR DOWN"] and current_action != last_sent_action:
                    emoji = "🚀" if current_action == "COMPRAR UP" else "📉"
                    msg = (
                        f"🚨 **SEÑAL KALSHI BTC 15M** 🚨\n"
                        f"**Acción:** 🔥 {current_action} {emoji}\n"
                        f"**Precio BTC:** ${btc_price:.2f}\n"
                        f"**Hora:** {now.strftime('%H:%M:%S')} UTC\n"
                        f"**Detalle:** {detail}"
                    )
                    send_discord_alert(msg)
                    last_sent_action = current_action

                # B) ALERTA DE INVALIDACIÓN / CERRAR POSICIÓN
                elif current_action == "NEUTRAL" and last_sent_action in ["COMPRAR UP", "COMPRAR DOWN"]:
                    msg = (
                        f"⚠️ **INVALIDACIÓN / CERRAR POSICIÓN** ⚠️\n"
                        f"**Precio BTC:** ${btc_price:.2f}\n"
                        f"**Hora:** {now.strftime('%H:%M:%S')} UTC\n"
                        f"**Motivo:** El mercado perdió fuerza o cambió de tendencia. Vende o sal del contrato ahora."
                    )
                    send_discord_alert(msg)
                    last_sent_action = "NEUTRAL"

        except Exception as e:
            print(f"[CRITICAL ERROR]: Excepción en el bucle principal: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
