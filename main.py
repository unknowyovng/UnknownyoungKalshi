import os
import time
import asyncio
import threading
import requests
from flask import Flask

# Configuración del servidor HTTP (Keep-Alive para Render)
app = Flask('')

@app.route('/', methods=['GET', 'HEAD'])
def home():
    return "Bot Cuantitativo de Ultra Alta Velocidad Activo.", 200

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        app.run(host='0.0.0.0', port=port, use_reloader=False)
    except Exception as e:
        print(f"Error en servidor HTTP: {e}")

def self_ping_loop():
    time.sleep(10)
    port = os.environ.get("PORT", "8080")
    url = os.environ.get("RENDER_EXTERNAL_URL", f"http://127.0.0.1:{port}/")
    while True:
        try:
            requests.get(url, timeout=5)
        except Exception:
            pass
        time.sleep(240)

# ==========================================
# DISCORD WEBHOOK
# ==========================================

DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL", 
    "https://discord.com/api/webhooks/1534228345645039680/OP6raerP1RlkCl6WJvJ_Vto9FSJ05i42xOtRDbhHY-6KPv3Wlmgg9yatZEb-gqmiXbsz"
)

def enviar_a_discord(mensaje):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        payload = {"content": mensaje}
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=3)
    except Exception as e:
        print(f"Error enviando a Discord: {e}")

# ==========================================
# MOTOR ULTRA RÁPIDO DE DIVERGENCIA (BINANCE VS KALSHI)
# ==========================================

seen_signals = set()

def obtener_fast_momo_binance():
    """Obtiene el delta de precio Spot de BTC en Binance en la última ventana corta."""
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=1"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            data = res.json()[0]
            open_p = float(data[1])
            close_p = float(data[4])
            return (close_p - open_p), close_p
    except Exception:
        pass
    return 0, 0

def fast_kalshi_scanner():
    """Escanea el orderbook de Kalshi a alta velocidad buscando descalces de precio."""
    global seen_signals
    
    delta_usd, spot_price = obtener_fast_momo_binance()
    if spot_price == 0:
        return

    try:
        # API de Kalshi directa para mercados de BTC
        url = "https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=20"
        res = requests.get(url, timeout=3)
        
        if res.status_code == 200:
            markets = res.json().get("markets", [])
            
            for m in markets:
                ticker = m.get("ticker", "")
                title = m.get("title", "")
                
                if "btc" in ticker.lower() or "kxbtc" in ticker.lower():
                    yes_ask = m.get("yes_ask", 0) or m.get("yes_bid", 0)
                    no_ask = 100 - yes_ask if yes_ask > 0 else 0
                    
                    # 1. ESCENARIO COMPRAR UP: Binance sube con fuerza pero Kalshi YES cotiza <= 20%
                    if delta_usd >= 15 and 0 < yes_ask <= 20:
                        signal_key = f"{ticker}_UP_{yes_ask}"
                        if signal_key not in seen_signals:
                            seen_signals.add(signal_key)
                            msg = (
                                f"⚡ **ALERTA ULTRA RÁPIDA: DIVERGENCIA DETECTADA** ⚡\n"
                                f"• **Mercado:** {title} (`{ticker}`)\n"
                                f"• **Binance Spot:** ${spot_price:,.2f} (Impulso: +${delta_usd:,.2f} USD)\n"
                                f"• **Cuota Kalshi YES:** {yes_ask}%\n"
                                f"🚨 **SEÑAL ESTRICTA:** **COMPRAR UP**\n"
                                f"🎯 **Objetivo Scalping:** Salida rápida al 40% - 50%\n"
                                f"🔗 https://kalshi.com/markets/{ticker.lower()}"
                            )
                            enviar_a_discord(msg)
                            print(f"[FAST BOT] SEÑAL ENVIADA: COMPRAR UP en {ticker}")

                    # 2. ESCENARIO COMPRAR DOWN: Binance cae con fuerza pero Kalshi NO cotiza <= 20%
                    elif delta_usd <= -15 and 0 < no_ask <= 20:
                        signal_key = f"{ticker}_DOWN_{no_ask}"
                        if signal_key not in seen_signals:
                            seen_signals.add(signal_key)
                            msg = (
                                f"⚡ **ALERTA ULTRA RÁPIDA: DIVERGENCIA DETECTADA** ⚡\n"
                                f"• **Mercado:** {title} (`{ticker}`)\n"
                                f"• **Binance Spot:** ${spot_price:,.2f} (Impulso: ${delta_usd:,.2f} USD)\n"
                                f"• **Cuota Kalshi NO:** {no_ask}%\n"
                                f"🚨 **SEÑAL ESTRICTA:** **COMPRAR DOWN**\n"
                                f"🎯 **Objetivo Scalping:** Salida rápida al 40% - 50%\n"
                                f"🔗 https://kalshi.com/markets/{ticker.lower()}"
                            )
                            enviar_a_discord(msg)
                            print(f"[FAST BOT] SEÑAL ENVIADA: COMPRAR DOWN en {ticker}")

    except Exception as e:
        print(f"Error en fast_kalshi_scanner: {e}")

def main_high_frequency_loop():
    enviar_a_discord("🚀 **BOT ULTRA RÁPIDO ACTIVO**: Escaneo directo por API habilitado. Señales estrictas **COMPRAR UP / DOWN**.")
    while True:
        try:
            fast_kalshi_scanner()
        except Exception as e:
            print(f"Error en el bucle principal: {e}")
        time.sleep(2)  # Escaneo cada 2 segundos para máxima velocidad

# ==========================================
# INICIALIZACIÓN
# ==========================================

if __name__ == "__main__":
    threading.Thread(target=run_http_server, daemon=True).start()
    threading.Thread(target=self_ping_loop, daemon=True).start()
    main_high_frequency_loop()
