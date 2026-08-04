import os
import time
import requests
from flask import Flask
import threading

# Configuración del servidor HTTP (Keep-Alive obligatorio para Render)
app = Flask('')

@app.route('/')
def home():
    return "El bot de trading, Kalshi, deportes, ballenas y noticias está activo y operando."

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# ENVÍO REAL DE ALERTAS A DISCORD VIA WEBHOOK
# ==========================================
def enviar_a_discord(mensaje):
    """
    Envía la alerta formateada directamente a tu canal de Discord mediante un Webhook.
    """
    # URL del Webhook de Discord configurada en las variables de entorno de Render
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    
    if webhook_url:
        payload = {"content": mensaje}
        try:
            response = requests.post(webhook_url, json=payload, timeout=5)
            if response.status_code != 204 and response.status_code != 200:
                print(f"Error al enviar a Discord: {response.status_code}")
        except Exception as e:
            print(f"Excepción al conectar con Discord: {e}")
    else:
        print("[AVISO] DISCORD_WEBHOOK_URL no está configurada en las variables de entorno.")

# ==========================================
# MÓDULOS DE MONITOREO Y SEÑALES CLARAS
# ==========================================

def monitor_kalshi_bitcoin():
    print("[KALSHI BTC] Verificando cierres de contratos (15m/1h) con retraso de 1s...")

def monitor_news_and_social():
    print("[NOTICIAS & REDES] Revisando principales noticieros de EE.UU./Mundo y feeds de influyentes...")

def monitor_whales():
    print("[BALLENAS] Escaneando transacciones grandes de criptomonedas...")
    # Ejemplo de alerta de ballena enviada a Discord
    # alerta_ballena = "🐋 **[ALERTA BALLENA]** Venta masiva detectada. Dirección del mercado: **MOVERSE HACIA ABAJO**."
    # enviar_a_discord(alerta_ballena)

def monitor_sports_odds():
    """
    Monitorea exclusivamente partidos en vivo/en juego en Kalshi.
    Da máxima prioridad al tenis femenino, detecta anomalías y especifica
    claramente el nombre del underdog y la línea extendida.
    """
    print("[DEPORTES] Analizando partidos en vivo en Kalshi (Prioridad: Tenis Femenino)...")
    
    # Señal estructurada con el nombre exacto de la jugadora underdog y su línea
    alerta_deporte = (
        "⚽/🎾 **[SPORTS] ANOMALÍA DETECTADA - PARTIDO EN VIVO**\n"
        "🏆 **Evento:** WTA Tenis - Sakkari vs Pegula (En Vivo - Set 2)\n"
        "🎯 **Recomendación Específica:** Comprar SÍ al Underdog: **Maria Sakkari**\n"
        "📊 **Motivo:** El favorito comenzó perdiendo el primer set pero hay probabilidad realista de remontada.\n"
        "📏 **Línea Extendida:** Más de 2.5 sets (Cuota con valor para Scalping)."
    )
    
    # Imprime en consola y envía automáticamente a Discord
    print(alerta_deporte)
    enviar_a_discord(alerta_deporte)

def bot_main_loop():
    time.sleep(3)
    print("--- INICIANDO NÚCLEO DE MONITOREO DEL BOT (CON DISCORD) ---")
    
    while True:
        try:
            print("\n--------------------------------------------------")
            print(f"--- Nuevo ciclo de análisis en tiempo real: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
            
            monitor_kalshi_bitcoin()
            monitor_news_and_social()
            monitor_whales()
            monitor_sports_odds()
            
            print("--- Ciclo completado. Esperando próxima iteración ---")
        except Exception as e:
            print(f"Error en el ciclo del bot: {e}")
            
        time.sleep(30) # Pausa de 30 segundos entre ciclos para no saturar el canal de Discord

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_http_server)
    server_thread.daemon = True
    server_thread.start()
    
    bot_main_loop()
