import os
import time
import requests
from flask import Flask
import threading

# Configuración del servidor HTTP (Keep-Alive para evitar caídas en Render)
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

URL_KALSHI_DEFAULT = "https://kalshi.com"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "TU_WEBHOOK_DE_DISCORD_AQUI")

def enviar_a_discord(mensaje):
    """
    Envía la alerta formateada directamente a tu canal de Discord mediante Webhook.
    """
    if "TU_WEBHOOK_DE_DISCORD" in DISCORD_WEBHOOK_URL:
        print(">>> [AVISO] Webhook de Discord no configurado.")
        return

    payload = {"content": mensaje}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"Error al conectar con Discord: {e}")

def generar_mensaje_apuestas(underdog_realista):
    url_evento = underdog_realista.get('enlace', URL_KALSHI_DEFAULT)
    nombre_evento = underdog_realista.get('nombre', 'Desconocido')
    recomendacion = underdog_realista.get('recomendacion', 'Sin recomendación')
    motivo = underdog_realista.get('motivo', 'Anomalía en directo')
    linea = underdog_realista.get('linea', 'Línea en vivo')

    mensaje = (
        f"🔥 **[SPORTS - EN VIVO] OPORTUNIDAD DETECTADA:**\n"
        f"• **Evento:** {nombre_evento}\n"
        f"• **Análisis/Recomendación:** {recomendacion}\n"
        f"• **Motivo:** {motivo}\n"
        f"• **Línea:** {linea}\n"
        f"• **Enlace Exacto del Juego:** {url_evento}"
    )
    return mensaje

def monitor_sports_odds():
    """
    Monitorea deportes y descarta automáticamente los eventos que ya finalizaron.
    """
    # Simulación de datos que llegan de la API de Kalshi
    evento_actual = {
        'nombre': 'WTA London - Sakkari vs Maria',
        'estado': 'Outcome determined', # <-- Aquí se detecta si el juego ya terminó
        'recomendacion': 'Comprar SÍ al Underdog',
        'motivo': 'Variación de cuotas',
        'linea': 'Scalping en vivo',
        'enlace': 'https://kalshi.com/markets/sakkari-vs-maria'
    }

    # FILTRO ESTRICTO: Si el evento ya determinó su resultado, se ignora por completo
    if evento_actual.get('estado') == 'Outcome determined':
        print(f">>> [IGNORADO] El evento '{evento_actual['nombre']}' ya finalizó (Outcome determined). No se envía señal.")
        return

    # Si el evento está activo, procede a enviar la alerta
    alerta = generar_mensaje_apuestas(evento_actual)
    print("\n----------------------------------------")
    print(alerta)
    print("----------------------------------------\n")
    enviar_a_discord(alerta)

def bot_main_loop():
    print(">>> Núcleo del bot de señales iniciado correctamente.")
    while True:
        try:
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
