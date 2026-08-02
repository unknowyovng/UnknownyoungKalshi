import os
import time
import asyncio
import threading
import requests
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands

# Variables de Entorno
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

POLL_INTERVAL = 3

# Estado Global
last_sent_action = "NEUTRAL"
last_sniper_action = "NONE"
current_target_price = None
manual_override_target = None  # Almacena el target manual via Discord
last_candle_block = None

# Configuración del Bot de Discord para leer comandos
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


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
        print(f"❌ Error al enviar alerta: {e}")


def get_btc_price():
    try:
        url = "https://api.exchange.coinbase.com/products/BTC-USD/ticker"
        res = requests.get(url, timeout=5).json()
        return float(res["price"])
    except Exception as e:
        print(f"⚠️ Error al obtener precio BTC: {e}")
        return None


def get_exact_kalshi_target_from_coinbase(now):
    try:
        block_start_dt = now.replace(second=0, microsecond=0)
        prev_minute_ts = int(block_start_dt.timestamp()) - 60

        url = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=60"
        res = requests.get(url, timeout=5).json()

        if isinstance(res, list) and len(res) > 0:
            target_candle = next((c for c in res if c[0] == prev_minute_ts), None)
            if target_candle:
                return float(target_candle[4])
            
            sorted_candles = sorted(res, key=lambda x: x[0], reverse=True)
            if len(sorted_candles) > 1:
                return float(sorted_candles[1][4])
            return float(sorted_candles[0][4])
    except Exception as e:
        print(f"⚠️ Error al obtener cierre histórico de Coinbase: {e}")
    return None


@bot.command(name="target")
async def set_target_command(ctx, value: str):
    """Comando de Discord: !target 63318.57  ó  !target auto"""
    global manual_override_target, current_target_price

    if value.lower() == "auto":
        manual_override_target = None
        await ctx.send("🤖 **Target restablecido a MODO AUTOMÁTICO.**")
        print("⚙️ Target cambiado a MODO AUTOMÁTICO por comando de Discord.")
    else:
        try:
            val = float(value)
            manual_override_target = val
            current_target_price = val
            await ctx.send(f"🎯 **Target fijado manualmente en:** `${val:.2f}`")
            print(f"⚙️ Target cambiado manualmente a ${val:.2f} por Discord.")
        except ValueError:
            await ctx.send("❌ Valor inválido. Usa un número (ejemplo: `!target 63318.57`) o `!target auto`.")


def evaluate_market(current_price, target_price, current_minute):
    global last_sniper_action

    diff = current_price - target_price
    abs_diff = abs(diff)

    # 🎯 DETECCIÓN SNIPER REVERSAL
    if 7 <= current_minute <= 13:
        if diff >= 8.0 and last_sent_action == "COMPRAR DOWN":
            if last_sniper_action != "SNIPE_UP":
                last_sniper_action = "SNIPE_UP"
                msg_sniper = (
                    f"⚡ **¡ALERTA SNIPER REVERSAL (x5 - x20)!** ⚡\n"
                    f"🔥 **COMPRAR UP DE EMERGENCIA / GIRO RAPIDO**\n"
                    f"**Precio BTC:** ${current_price:.2f}\n"
                    f"**Target:** ${target_price:.2f}\n"
                    f"**Desviación:** +${diff:.2f}"
                )
                send_discord_alert(msg_sniper)

        elif diff <= -8.0 and last_sent_action == "COMPRAR UP":
            if last_sniper_action != "SNIPE_DOWN":
                last_sniper_action = "SNIPE_DOWN"
                msg_sniper = (
                    f"⚡ **¡ALERTA SNIPER REVERSAL (x5 - x20)!** ⚡\n"
                    f"🔥 **COMPRAR DOWN DE EMERGENCIA / GIRO RAPIDO**\n"
                    f"**Precio BTC:** ${current_price:.2f}\n"
                    f"**Target:** ${target_price:.2f}\n"
                    f"**Desviación:** -${abs_diff:.2f}"
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


def main_loop():
    global last_sent_action, last_sniper_action, current_target_price, last_candle_block, manual_override_target

    while True:
        try:
            now = datetime.now(timezone.utc)
            current_minute = now.minute % 15
            candle_block = now.minute // 15

            btc_price = get_btc_price()

            if btc_price is not None:
                # Si hay override manual activo
                if manual_override_target is not None:
                    current_target_price = manual_override_target
                else:
                    # Modo Automático Normal
                    if candle_block != last_candle_block or current_target_price is None:
                        if current_minute == 0:
                            exact_target = get_exact_kalshi_target_from_coinbase(now)
                            if exact_target is not None:
                                current_target_price = exact_target
                                print(f"📌 [TARGET KALSHI EXACTO FIJADO]: ${current_target_price:.2f}")
                            else:
                                current_target_price = btc_price
                        last_candle_block = candle_block
                        last_sent_action = "NEUTRAL"
                        last_sniper_action = "NONE"

                if current_target_price is not None:
                    action, detail = evaluate_market(btc_price, current_target_price, current_minute)

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

                    print(f"[{now.strftime('%H:%M:%S')}] BTC: ${btc_price:.2f} | Target: ${current_target_price:.2f} | ACCIÓN: {action}")

        except Exception as e:
            print(f"❌ ERROR EN BUCLE PRINCIPAL: {e}")

        time.sleep(POLL_INTERVAL)


def run_bot():
    if DISCORD_BOT_TOKEN:
        # Hilo secundario para el loop del bot de Kalshi
        threading.Thread(target=main_loop, daemon=True).start()
        # Iniciar el cliente de Discord para escuchar comandos
        bot.run(DISCORD_BOT_TOKEN)
    else:
        print("⚠️ No se detectó DISCORD_BOT_TOKEN. Ejecutando solo bucle directo...")
        main_loop()


if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    run_bot()
