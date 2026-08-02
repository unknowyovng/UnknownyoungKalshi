import os
import time
import requests
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Configuración de Discord Webhook desde variables de entorno
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
POLL_INTERVAL = 15  # Consultar cada 15 segundos

# Variables globales para control de estado
last_sent_action = "NEUTRAL"
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
    try:
        url = "https://api.exchange.coinbase.com/products/BTC-USD/ticker"
        res = requests.get(url, timeout=5).json()
        return float(res["price"])
    except Exception as e:
        print(f"⚠️ Error al obtener precio BTC: {e}")
        return None


def fetch_exact_target(now, candle_block, is_block_start):
    """Busca el Target exacto probando Coinbase Spot Ticker y Velas Históricas."""
    # Si estamos justo al inicio de bloque (:00, :15, :30, :45), la prioridad es el primer ticker
    if is_block_start:
        for _ in range(3):
            price = get_btc_price()
            if price is not None:
                return price, "TICKER EN VIVO (:00)"
            time.sleep(1)

    # Si es a mitad de bloque (reinicio), buscamos la vela del inicio del bloque
    try:
        block_start_dt = now.replace(minute=(candle_block * 15), second=0, microsecond=0)
        block_start_ts = int(block_start_dt.timestamp())

        candles_url = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=60"
        c_res = requests.get(candles_url, timeout=5).json()

        if isinstance(c_res, list) and len(c_res) > 0:
            # Buscar la vela cuya hora de inicio corresponda al inicio de bloque
            target_candle = next((c for c in c_res if c[0] == block_start_ts), None)
            if target_candle:
                return float(target_candle[3]), "HISTÓRICO DE VELA (:00)"
            
            # Si es muy reciente y no ha generado la vela exacta, tomar la más cercana al bloque
            for candle in c_res:
                if candle[0] <= block_start_ts:
                    return float(candle[3]), "VELA HISTÓRICA CERCANA"
    except Exception as e:
        print(f"⚠️ Error al consultar velas históricas: {e}")

    # Respaldo final si falla lo demás
    spot = get_btc_price()
    return spot, "SPOT RESPALDO"


def evaluate_market(current_price, target_price, current_minute):
    diff = current_price - target_price
    abs_diff = abs(diff)

    if current_minute >= 12:
        if abs_diff < 15:
            return "NEUTRAL", f"Mercado muy ajustado cerca del Target (Diferencia: ${diff:+.2f})"
        elif diff > 0:
            return "COMPRAR UP", f"Cierre fuerte Alcista (+${diff:.2f} sobre Target) | min {current_minute}/15"
        else:
            return "COMPRAR DOWN", f"Cierre fuerte Bajista (${abs_diff:.2f} bajo Target) | min {current_minute}/15"
    elif current_minute >= 5:
        if diff >= 20:
            return "COMPRAR UP", f"Impulso Alcista (+${diff:.2f} sobre Target) | min {current_minute}/15"
        elif diff <= -20:
            return "COMPRAR DOWN", f"Tendencia Bajista (${abs_diff:.2f} bajo Target) | min {current_minute}/15"
        else:
            return "NEUTRAL", f"Sin tendencia clara (+${diff:.2f} del Target) | min {current_minute}/15"
    else:
        if diff >= 35:
            return "COMPRAR UP", f"Ruptura Alcista Temprana (+${diff:.2f} sobre Target) | min {current_minute}/15"
        elif diff <= -35:
            return "COMPRAR DOWN", f"Caída Temprana (${abs_diff:.2f} bajo Target) | min {current_minute}/15"
        else:
            return "NEUTRAL", f"Fase de inicio de vela (Diferencia: ${diff:+.2f}) | min {current_minute}/15"


def main():
    global last_sent_action, current_target_price, last_candle_block

    # Iniciar servidor web dummy para Render
    threading.Thread(target=run_dummy_server, daemon=True).start()

    print("🚀 Bot Kalshi 15m iniciado con éxito.")
    send_discord_alert("🟢 **BOT CONECTADO**\nBot iniciado correctamente y monitoreando mercado.")

    while True:
        try:
            now = datetime.now(timezone.utc)
            current_minute = now.minute % 15
            candle_block = now.minute // 15
            is_block_start = (current_minute == 0 and now.second < 20)

            btc_price = get_btc_price()

            if btc_price is not None:
                # Fijar Target al inicio de cada vela de 15m o si no hay Target guardado
                if candle_block != last_candle_block or current_target_price is None:
                    target_val, source_info = fetch_exact_target(now, candle_block, is_block_start)
                    
                    if target_val is not None:
                        current_target_price = target_val
                    else:
                        current_target_price = btc_price

                    last_candle_block = candle_block
                    last_sent_action = "NEUTRAL"
                    print(f"📌 [TARGET FIJADO - {source_info}]: ${current_target_price:.2f} para bloque {candle_block * 15}m")

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
