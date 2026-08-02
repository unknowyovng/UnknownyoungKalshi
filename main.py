import os
import time
import requests
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Configuración de Discord Webhook desde variables de entorno
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# Frecuencia ultra-rápida (cada 3 segundos) para monitoreo continuo
POLL_INTERVAL = 3  

# Variables globales para control de estado
last_sent_action = "NEUTRAL"
last_sniper_action = "NONE"
current_target_price = None
last_candle_block = None


class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot Kalshi 15m activo")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()


def send_discord_alert(msg):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
    except Exception as e:
        print(f"❌ Error al enviar alerta a Discord: {e}")


def get_btc_price():
    """Obtiene el precio Spot actual de BTC desde Coinbase Ticker."""
    try:
        url = "https://api.exchange.coinbase.com/products/BTC-USD/ticker"
        res = requests.get(url, timeout=5).json()
        return float(res["price"])
    except Exception as e:
        print(f"⚠️ Error al obtener precio BTC: {e}")
        return None


def get_exact_kalshi_target_from_coinbase(now):
    """
    Obtiene el precio de cierre de la vela del minuto :59 exacto de Coinbase,
    que corresponde al 'Price to beat' oficial asignado por Kalshi.
    """
    try:
        block_start_dt = now.replace(second=0, microsecond=0)
        prev_minute_ts = int(block_start_dt.timestamp()) - 60

        url = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=60"
        res = requests.get(url, timeout=5).json()

        if isinstance(res, list) and len(res) > 0:
            target_candle = next((c for c in res if c[0] == prev_minute_ts), None)
            if target_candle:
                return float(target_candle[4])  # Close exacto
            
            sorted_candles = sorted(res, key=lambda x: x[0], reverse=True)
            if len(sorted_candles) > 1:
                return float(sorted_candles[1][4])
            return float(sorted_candles[0][4])
    except Exception as e:
        print(f"⚠️ Error al obtener cierre histórico de Coinbase: {e}")
    return None


def fetch_candle_open_price(candle_block, now):
    """
    Obtiene la cotización de apertura de la vela del bloque de 15m actual
    en caso de que el bot se reinicie a mitad de bloque.
    """
    try:
        block_start_dt = now.replace(minute=(candle_block * 15), second=0, microsecond=0)
        block_start_ts = int(block_start_dt.timestamp())

        candles_url = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=60"
        c_res = requests.get(candles_url, timeout=5).json()

        if isinstance(c_res, list) and len(c_res) > 0:
            target_candle = next((c for c in c_res if c[0] == block_start_ts), None)
            if target_candle:
                return float(target_candle[3])  # Open price exacto
            
            sorted_candles = sorted(c_res, key=lambda x: x[0])
            for c in sorted_candles:
                if c[0] >= block_start_ts:
                    return float(c[3])
    except Exception as e:
        print(f"⚠️ Error buscando apertura histórica: {e}")
    return None


def evaluate_market(current_price, target_price, current_minute):
    """
    Evaluación dual:
    1. Señal estándar de entrada temprana.
    2. Detección de oportunidades Sniper Reversal (x5 a x20+).
    """
    global last_sniper_action

    diff = current_price - target_price
    abs_diff = abs(diff)

    # 🎯 DETECCIÓN SNIPER REVERSAL (x5 - x20)
    # Si estamos en minutos avanzados (min 7 a 13) y ocurre un cruce fuerte en el sentido contrario
    if 7 <= current_minute <= 13:
        if diff >= 8.0 and last_sent_action == "COMPRAR DOWN":
            # Estaba marcando DOWN y de repente cruzó hacia arriba: Oportunidad UP baratísima
            if last_sniper_action != "SNIPE_UP":
                last_sniper_action = "SNIPE_UP"
                msg_sniper = (
                    f"⚡ **¡ALERTA SNIPER REVERSAL (x5 - x20)!** ⚡\n"
                    f"🔥 **COMPRAR UP DE EMERGENCIA / GIRO RAPIDO**\n"
                    f"**Precio BTC:** ${current_price:.2f}\n"
                    f"**Target:** ${target_price:.2f}\n"
                    f"**Desviación:** +${diff:.2f}\n"
                    f"💰 *El contrato UP debe estar cotizando extremadamente barato (3¢ - 15¢).* "
                    f"Potencial de retorno masivo si se sostiene."
                )
                send_discord_alert(msg_sniper)

        elif diff <= -8.0 and last_sent_action == "COMPRAR UP":
            # Estaba marcando UP y de repente cruzó hacia abajo: Oportunidad DOWN baratísima
            if last_sniper_action != "SNIPE_DOWN":
                last_sniper_action = "SNIPE_DOWN"
                msg_sniper = (
                    f"⚡ **¡ALERTA SNIPER REVERSAL (x5 - x20)!** ⚡\n"
                    f"🔥 **COMPRAR DOWN DE EMERGENCIA / GIRO RAPIDO**\n"
                    f"**Precio BTC:** ${current_price:.2f}\n"
                    f"**Target:** ${target_price:.2f}\n"
                    f"**Desviación:** -${abs_diff:.2f}\n"
                    f"💰 *El contrato DOWN debe estar cotizando extremadamente barato (3¢ - 15¢).* "
                    f"Potencial de retorno masivo si se sostiene."
                )
                send_discord_alert(msg_sniper)

    # PROTECCIÓN DE CIERRE (Minutos 13 y 14)
    if current_minute >= 13:
        if abs_diff < 15.0:
            return "NEUTRAL", f"⚠️ ZONA DE RIESGO DE LATIGAZO (Cierre ajustado: ${diff:+.2f}) | min {current_minute}/15"

    # GATILLO SENSIBLE DE ENTRADA TEMPRANA
    if diff >= 5.0:
        return "COMPRAR UP", f"⚡ Entrada Temprana (+${diff:.2f} sobre Target) | min {current_minute}/15"
    elif diff <= -5.0:
        return "COMPRAR DOWN", f"⚡ Entrada Temprana (${abs_diff:.2f} bajo Target) | min {current_minute}/15"
    else:
        return "NEUTRAL", f"Esperando ruptura (${diff:+.2f} del Target) | min {current_minute}/15"


def main():
    global last_sent_action, last_sniper_action, current_target_price, last_candle_block

    # Iniciar servidor web dummy para Render
    threading.Thread(target=run_dummy_server, daemon=True).start()

    print("🚀 Bot Kalshi 15m iniciado con detector Sniper Reversal (x5 - x20).")
    send_discord_alert("🟢 **BOT CONECTADO**\nMotor configurado con alertas Sniper Reversal de alto multiplicador.")

    while True:
        try:
            now = datetime.now(timezone.utc)
            current_minute = now.minute % 15
            candle_block = now.minute // 15

            btc_price = get_btc_price()

            if btc_price is not None:
                # Fijar Target al inicio del nuevo bloque o si el bot recién arranca
                if candle_block != last_candle_block or current_target_price is None:
                    if current_minute == 0:
                        exact_target = get_exact_kalshi_target_from_coinbase(now)
                        if exact_target is not None:
                            current_target_price = exact_target
                            print(f"📌 [TARGET KALSHI EXACTO FIJADO]: ${current_target_price:.2f} para bloque {candle_block * 15}m")
                        else:
                            current_target_price = btc_price
                            print(f"📌 [TARGET SPOT RESPALDO FIJADO]: ${current_target_price:.2f} para bloque {candle_block * 15}m")
                    else:
                        open_price = fetch_candle_open_price(candle_block, now)
                        if open_price is not None:
                            current_target_price = open_price
                            print(f"📌 [TARGET HISTÓRICO REINICIO FIJADO]: ${current_target_price:.2f} para bloque {candle_block * 15}m")
                        else:
                            current_target_price = btc_price
                            print(f"📌 [TARGET SPOT RESPALDO FIJADO]: ${current_target_price:.2f} para bloque {candle_block * 15}m")

                    last_candle_block = candle_block
                    last_sent_action = "NEUTRAL"
                    last_sniper_action = "NONE"

                # Evaluar mercado
                action, detail = evaluate_market(btc_price, current_target_price, current_minute)

                # Notificar a Discord si la acción cambia
                if action != last_sent_action:
                    emoji = "🚀" if action == "COMPRAR UP" else ("📉" if action == "COMPRAR DOWN" else "⚪")
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

                # Log de control en Render
                print(f"[{now.strftime('%H:%M:%S')}] BTC: ${btc_price:.2f} | Target: ${current_target_price:.2f} | ACCIÓN: {action} ({detail})")

        except Exception as e:
            print(f"❌ ERROR EN BUCLE PRINCIPAL: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
