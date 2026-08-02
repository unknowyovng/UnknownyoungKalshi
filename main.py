import os
import time
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

# ==========================================
# SERVIDOR WEB PARA RENDER (RESPUESTA 200 OK)
# ==========================================
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return  # Desactiva logs HTTP para no ensuciar la consola de Render

def run_dummy_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# ==========================================
# CONFIGURACIÓN Y VARIABLES DE ENTORNO
# ==========================================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "PEGA_AQUI_TU_WEBHOOK_DE_DISCORD")
POLL_INTERVAL = 10  # Frecuencia de chequeo en segundos (10s)

# Estado global del bot
last_sent_action = "NEUTRAL"
current_target_price = None  # Se actualiza automáticamente al inicio de cada vela de 15m
last_candle_block = -1

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

# ==========================================
# EVALUACIÓN DE SEÑALES Y REGLAS DE NEGOCIO
# ==========================================
def evaluate_market(current_price, target_price, current_minute):
    """
    Calcula la acción con márgenes limpios y sin bloqueos de distancia excesiva.
    """
    # 1. Filtro de seguridad para minutos finales (Cooldown en minutos 13 y 14)
    if current_minute >= 13:
        return "NEUTRAL", "Final de bloque (Cuota baja / Cooldown)"

    # 2. Si aún no se ha fijado el Target del bloque
    if target_price is None:
        return "NEUTRAL", "Esperando fijar Target Price del bloque"

    diferencia = current_price - target_price  # Positivo = por encima | Negativo = por debajo

    # 3. Condición de Entrada UP (BTC está al menos $2.00 por encima del Target)
    if diferencia >= 8.0:
        return "COMPRAR UP", f"Impulso Alcista (+${diferencia:.2f} sobre Target) | min {current_minute}/15"
    
    # 4. Condición de Entrada DOWN (BTC cae $5.00 o más por debajo del Target)
    elif diferencia <= -11.0:
        return "COMPRAR DOWN", f"Tendencia Bajista (${abs(diferencia):.2f} bajo Target) | min {current_minute}/15"

    # 5. Zona Neutral
    return "NEUTRAL", f"Mercado cerca del Target (Diferencia: ${diferencia:+.2f})"

# ==========================================
# BUCLE PRINCIPAL (MAIN LOOP)
# ==========================================
def main():
    global last_sent_action, current_target_price, last_candle_block
    
    # Iniciar servidor web dummy para Render
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    print("🚀 Bot Kalshi 15m iniciado con éxito.")
    send_discord_alert("🟢 **BOT CONECTADO**\nBot iniciado correctamente y monitoreando mercado.")

    while True:
        try:
            now = datetime.now(timezone.utc)
            current_minute = now.minute % 15   # Minuto relativo (0 a 14)
            candle_block = now.minute // 15     # Identificador de bloque (0, 1, 2, 3)
            
            btc_price = get_btc_price()

            if btc_price is not None:
                # Fijar Target al inicio de cada vela de 15m
                if candle_block != last_candle_block or current_target_price is None:
                    current_target_price = btc_price
                    last_candle_block = candle_block
                    last_sent_action = "NEUTRAL"
                    print(f"🎯 [NUEVO TARGET FIJADO]: ${current_target_price:.2f} para el bloque {candle_block * 15}m")

                current_action, detail = evaluate_market(btc_price, current_target_price, current_minute)

                # Log en consola de Render
                print(f"[{now.strftime('%H:%M:%S')}] BTC: ${btc_price:.2f} | Target: ${current_target_price:.2f} | ACCIÓN: {current_action} ({detail})")

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
                        f"**Target a Vencer:** ${current_target_price:.2f}\n"
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
                        f"**Target:** ${current_target_price:.2f}\n"
                        f"**Hora:** {now.strftime('%H:%M:%S')} UTC\n"
                        f"**Motivo:** El mercado perdió fuerza o cambió de tendencia. Vende o sal del contrato ahora."
                    )
                    send_discord_alert(msg)
                    last_sent_action = "NEUTRAL"

        except Exception as e:
            print(f"[CRITICAL ERROR]: Excepción en el bucle principal: {e}")

        time.sleep(POLL_INTERVAL)


def main():
    global last_sent_action, current_target_price, last_candle_block

    # Iniciar servidor web dummy para Render
    threading.Thread(target=run_dummy_server, daemon=True).start()

    print("🚀 Bot Kalshi 15m iniciado con éxito.")
    send_discord_alert("🟢 **BOT CONECTADO**\nBot iniciado correctamente y monitoreando mercado.")

    while True:
        try:
            now = datetime.now(timezone.utc)
            current_minute = now.minute % 15   # Minuto relativo (0 a 14)
            candle_block = now.minute // 15    # Identificador de bloque (0, 1, 2, 3)

            btc_price = get_btc_price()

            if btc_price is not None:
                # Fijar Target al inicio de cada vela de 15m o en un reinicio
                if candle_block != last_candle_block or current_target_price is None:
                    # Si estamos en el minuto 0 exacto, el precio actual es el de apertura
                    if current_minute == 0:
                        current_target_price = btc_price
                    else:
                        # Si el bot se reinició a mitad de bloque, obtenemos el precio de apertura oficial de Coinbase
                        try:
                            start_time = now.replace(minute=(candle_block * 15), second=0, microsecond=0)
                            iso_start = start_time.isoformat()
                            candles_url = f"https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=900&start={iso_start}&end={iso_start}"
                            c_res = requests.get(candles_url, timeout=5).json()
                            if isinstance(c_res, list) and len(c_res) > 0:
                                current_target_price = float(c_res[0][3]) # Precio de apertura (open)
                            else:
                                current_target_price = btc_price
                        except Exception as e:
                            print(f"⚠️ No se pudo obtener vela de apertura, usando precio actual: {e}")
                            current_target_price = btc_price

                    last_candle_block = candle_block
                    last_sent_action = "NEUTRAL"
                    print(f"🎯 [TARGET FIJADO]: ${current_target_price:.2f} para el bloque {candle_block * 15}m")

                # Evaluar mercado
                action, detail = evaluate_market(btc_price, current_target_price, current_minute)

                # Notificar a Discord si la acción cambia respecto a la última enviada
                if action != last_sent_action:
                    emoji = "🚀" if action == "COMPRAR UP" else ("📉" if action == "COMPRAR DOWN" else "⚖️")
                    msg = (
                        f"🚨 **SEÑAL KALSHI BTC 15M** 🚨\n"
                        f"**Acción:** 🔥 {action} {emoji}\n"
                        f"**Precio BTC:** ${btc_price:.2f}\n"
                        f"**Target a Vencer:** ${current_target_price:.2f}\n"
                        f"**Hora:** {now.strftime('%H:%M:%S')} UTC\n"
                        f"**Detalle:** {detail}"
                    )
                    send_discord_alert(msg)
                    last_sent_action = action

        except Exception as e:
            print(f"❌ ERROR EN BUCLE PRINCIPAL: {e}")

       time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
