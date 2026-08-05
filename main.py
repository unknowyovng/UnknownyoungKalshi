import os
import time
import threading
import requests
from flask import Flask

# Inicialización de la App Flask (Health Check para Render)
app = Flask(__name__)
PORT = int(os.environ.get("PORT", 8080))

@app.route('/', methods=['GET', 'HEAD'])
def home():
    return "Bot Cuantitativo de Ultra Alta Velocidad Activo.", 200

def run_http_server():
    try:
        app.run(host='0.0.0.0', port=PORT, use_reloader=False)
    except Exception as e:
        print(f"Error en servidor HTTP: {e}")

def self_ping_loop():
    time.sleep(10)
    url = os.environ.get("RENDER_EXTERNAL_URL", f"http://127.0.0.1:{PORT}/")
    while True:
        try:
            requests.get(url, timeout=5)
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
# MOTOR CUANTITATIVO: PROBABILIDAD REAL VS KALSHI
# ==========================================

seen_signals = set()

def obtener_momo_binance():
    """Obtiene la variación de precio en Binance Spot y la velocidad de la vela actual."""
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=2"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            data = res.json()
            # Vela actual de 1m
            open_p = float(data[-1][1])
            close_p = float(data[-1][4])
            delta_usd = close_p - open_p
            return delta_usd, close_p
    except Exception:
        pass
    return 0, 0

def fast_kalshi_scanner():
    """Analiza la probabilidad real en Binance y emite COMPRAR UP o DOWN sin importar el %."""
    global seen_signals
    
    delta_usd, spot_price = obtener_momo_binance()
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
                    
                    # 1. EVALUACIÓN COMPRAR UP (Impulso alcista claro en Binance)
                    if delta_usd >= 10:
                        tipo_alerta = "🔥 **ALTA CONVICCIÓN (PRECIO BAJO)**" if yes_ask <= 20 else "📈 **IMPULSO A FAVOR DE TENDENCIA**"
                        signal_key = f"{ticker}_UP_{int(yes_ask/5)}"  # Evita duplicados continuos en un mismo rango
                        
                        if signal_key not in seen_signals:
                            seen_signals.add(signal_key)
                            msg = (
                                f"⚡ **SEÑAL DE PROBABILIDAD REAL (15M)** ⚡\n"
                                f"• **Mercado:** {title} (`{ticker}`)\n"
                                f"• **Binance Spot:** ${spot_price:,.2f} (Delta 1m: +${delta_usd:,.2f} USD)\n"
                                f"• **Cuota Kalshi YES:** {yes_ask}%\n"
                                f"• **Tipo de Alerta:** {tipo_alerta}\n"
                                f"🚨 **INSTRUCCIÓN ESTRICTA:** **COMPRAR UP**\n"
                                f"🎯 **Objetivo de Salida:** +20% a +40% de la cuota de entrada\n"
                                f"🔗 https://kalshi.com/markets/{ticker.lower()}"
                            )
                            enviar_a_discord(msg)
                            print(f"[QUANT BOT] SEÑAL DISPARADA: COMPRAR UP en {ticker}")

                    # 2. EVALUACIÓN COMPRAR DOWN (Impulso bajista claro en Binance)
                    elif delta_usd <= -10:
                        tipo_alerta = "🔥 **ALTA CONVICCIÓN (PRECIO BAJO)**" if no_ask <= 20 else "📉 **IMPULSO A FAVOR DE TENDENCIA**"
                        signal_key = f"{ticker}_DOWN_{int(no_ask/5)}"
                        
                        if signal_key not in seen_signals:
                            seen_signals.add(signal_key)
                            msg = (
                                f"⚡ **SEÑAL DE PROBABILIDAD REAL (15M)** ⚡\n"
                                f"• **Mercado:** {title} (`{ticker}`)\n"
                                f"• **Binance Spot:** ${spot_price:,.2f} (Delta 1m: ${delta_usd:,.2f} USD)\n"
                                f"• **Cuota Kalshi NO:** {no_ask}%\n"
                                f"• **Tipo de Alerta:** {tipo_alerta}\n"
                                f"🚨 **INSTRUCCIÓN ESTRICTA:** **COMPRAR DOWN**\n"
                                f"🎯 **Objetivo de Salida:** +20% a +40% de la cuota de entrada\n"
                                f"🔗 https://kalshi.com/markets/{ticker.lower()}"
                            )
                            enviar_a_discord(msg)
                            print(f"[QUANT BOT] SEÑAL DISPARADA: COMPRAR DOWN en {ticker}")

    except Exception as e:
        print(f"Error en fast_kalshi_scanner: {e}")

def main_high_frequency_loop():
    enviar_a_discord("🚀 **BOT ACTUALIZADO**: Lectura de Probabilidad Real activa. Emitiendo **COMPRAR UP/DOWN** sin restricción de cuota.")
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
    threading.Thread(target=run_http_server, daemon=True).start()
    threading.Thread(target=self_ping_loop, daemon=True).start()
    main_high_frequency_loop()
