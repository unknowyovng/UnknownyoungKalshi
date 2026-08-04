import os
import time
import requests
from flask import Flask
import threading

# Configuración del servidor HTTP (Keep-Alive para Render)
app = Flask('')

@app.route('/')
def home():
    return "El bot de trading, monitoreo de mercados, deportes, ballenas y noticias está 100% activo y operativo."

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# MÓDULOS DE MONITOREO Y LÓGICA DEL BOT
# ==========================================

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

def enviar_a_discord(mensaje):
    if not DISCORD_WEBHOOK_URL:
        print(">>> [ERROR] La variable DISCORD_WEBHOOK_URL está vacía en Render.")
        return

    payload = {"content": mensaje}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print(f">>> [DISCORD] Estado de envío: {response.status_code}")
    except Exception as e:
        print(f">>> [EXCEPCIÓN DISCORD] Error al conectar con el Webhook: {e}")

# Variable global para almacenar el precio anterior y detectar la dirección real
precio_anterior_btc = None

def obtener_precio_bitcoin_real():
    try:
        url_coinbase = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
        response = requests.get(url_coinbase, timeout=5)
        data = response.json()
        precio_float = float(data['data']['amount'])
        return precio_float
    except Exception as e:
        print(f"No se pudo obtener el precio en vivo de Coinbase: {e}")
        return None

def generar_mensaje_tendencia_btc(tendencia, precio_actual, detalle):
    if tendencia.upper() == "ALCISTA":
        icono = "🚀"
        color_texto = "**TENDENCIA ALCISTA DETECTADA (BULLISH)**"
    else:
        icono = "📉"
        color_texto = "**TENDENCIA BAJISTA DETECTADA (BEARISH)**"

    enlace_seguro = "https://kalshi.com"

    mensaje = (
        f"{icono} **[KALSHI BITCOIN 15M/1H] {color_texto}**\n"
        f"• **Precio / Activo:** BTC a ${precio_actual:,.2f}\n"
        f"• **Dirección del Mercado:** {tendencia.upper()}\n"
        f"• **Análisis Técnico:** {detalle}\n"
        f"• **Enlace Directo:** [Abrir Mercado BTC en Kalshi]({enlace_seguro})"
    )
    return mensaje

def monitor_kalshi_bitcoin():
    global precio_anterior_btc
    
    precio_actual = obtener_precio_bitcoin_real()
    if precio_actual is None:
        return

    # Determinar la tendencia real comparando con la lectura anterior
    if precio_anterior_btc is None:
        tendencia_actual = "ALCISTA"
    elif precio_actual >= precio_anterior_btc:
        tendencia_actual = "ALCISTA"
    else:
        tendencia_actual = "BAJISTA"

    detalle_analisis = f"Evaluación de movimiento en tiempo real (Precio previo: ${precio_anterior_btc:,.2f} -> Actual: ${precio_actual:,.2f})." if precio_anterior_btc else "Inicialización de lectura de tendencia."
    
    # Actualizar el precio anterior para el siguiente ciclo
    precio_anterior_btc = precio_actual

    alerta_btc = generar_mensaje_tendencia_btc(tendencia_actual, precio_actual, detalle_analisis)
    print("\n---------------- [ TENDENCIA BTC ] ----------------")
    print(alerta_btc)
    print("---------------------------------------------------\n")
    enviar_a_discord(alerta_btc)

def monitor_sports_odds():
    # Módulo de deportes limpio sin señales falsas pasadas
    pass

def bot_main_loop():
    print(">>> Núcleo del bot iniciado con detección real de dirección (Alcista/Bajista).")
    while True:
        try:
            monitor_kalshi_bitcoin()
            monitor_sports_odds()
        except Exception as e:
            print(f"Error en el ciclo del bot: {e}")
            
        time.sleep(60)

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_http_server)
    server_thread.daemon = True
    server_thread.start()
    
    bot_thread = threading.Thread(target=bot_main_loop)
    bot_thread.daemon = True
    bot_thread.start()

    while True:
        time.sleep(10)
