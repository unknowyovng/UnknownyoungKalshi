import os
import time
import threading
import requests
from flask import Flask

# Inicialización de la App Flask
app = Flask(__name__)

# Render pasa automáticamente la variable PORT, usamos 8080 por defecto
PORT = int(os.environ.get("PORT", 8080))

@app.route('/', methods=['GET', 'HEAD'])
def home():
    """Respuesta rápida para el Health Check de Render."""
    return "Bot Cuantitativo de Ultra Alta Velocidad Activo.", 200

def run_http_server():
    """Ejecuta el servidor web en el host 0.0.0.0 y puerto asignado."""
    try:
        app.run(host='0.0.0.0', port=PORT, use_reloader=False)
    except Exception as e:
        print(f"Error en servidor HTTP: {e}")

def self_ping_loop():
    """Mantiene la instancia despierta enviando un ping interno cada 3 minutos."""
    time.sleep(10)
    url = os.environ.get("RENDER_EXTERNAL_URL", f"http://127.0.0.1:{PORT}/")
    print(f"[SELF-PING] Servicio activo apuntando a: {url}")
    while True:
        try:
            requests.get(url, timeout=5)
            print("[SELF-PING] Ping de mantenimiento OK")
        except Exception:
            pass
        time.sleep(180)

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
    """Obtiene la variación de precio en Binance Spot en la última vela."""
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
    """Escanea el orderbook de Kalshi vía API a máxima velocidad."""
    global seen_signals
    
    delta_usd, spot_price = obtener_fast_momo_binance()
    if spot_price == 0:
        return

    try:
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
                    
                    # 1. ESCENARIO COMPRAR UP: Impulso alcista en Binance y cuota YES castigada
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

                    # 2. ESCENARIO COMPRAR DOWN: Impulso bajista en Binance y cuota NO castigada
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
    enviar_a_discord("🚀 **BOT ULTRA RÁPIDO REINICIADO**: Servidor HTTP en puerto activo y escaneo listo.")
    while True:
        try:
            fast_kalshi_scanner()
        except Exception as e:
            print(f"Error en bucle principal: {e}")
        time.sleep(2)

# ==========================================
# INICIALIZACIÓN DE HILOS
# ==========================================

if __name__ == "__main__":
    # Arrancar Servidor Web
    t_server = threading.Thread(target=run_http_server, daemon=True)
    t_server.start()

    # Arrancar Ping de Mantenimiento
    t_ping = threading.Thread(target=self_ping_loop, daemon=True)
    t_ping.start()

    # Iniciar Bucle de Monitoreo
    main_high_frequency_loop()
