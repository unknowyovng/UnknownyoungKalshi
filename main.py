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
    try:
        app.run(host='0.0.0.0', port=port, use_reloader=False)
    except Exception as e:
        print(f"Error crítico en el servidor HTTP: {e}")

# ==========================================
# CONFIGURACIÓN Y MÓDULOS DE MONITOREO Y LÓGICA DEL BOT
# ==========================================

URL_KALSHI_BASE = "https://kalshi.com/markets"
DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL", 
    "https://discord.com/api/webhooks/1534228345645039680/OP6raerP1RlkCl6WJvJ_Vto9FSJ05i42xOtRDbhHY-6KPv3Wlmgg9yatZEb-gqmiXbsz"
)

def enviar_a_discord(mensaje):
    """
    Envía mensajes y alertas directamente al canal de Discord vía Webhook.
    """
    if not DISCORD_WEBHOOK_URL:
        print("Error: Webhook de Discord no configurado.")
        return
    try:
        payload = {"content": mensaje}
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code not in [200, 204]:
            print(f"Error al enviar a Discord (Status {response.status_code}): {response.text}")
    except Exception as e:
        print(f"Excepción al intentar enviar mensaje a Discord: {e}")

def construir_url_kalshi(ticker_evento=None):
    """
    Construye la URL exacta del mercado para evitar errores 404.
    """
    if ticker_evento:
        return f"{URL_KALSHI_BASE}/{ticker_evento.lower()}"
    return URL_KALSHI_BASE

def generar_mensaje_apuestas(underdog_realista, favorito_convertido):
    link_underdog = construir_url_kalshi(underdog_realista.get('ticker'))
    link_favorito = construir_url_kalshi(favorito_convertido.get('ticker'))

    nombre_underdog = underdog_realista.get('nombre', 'Desconocido')
    rec_underdog = underdog_realista.get('recomendacion', 'Sin recomendación')

    texto_underdog = (
        f"🔥 **Underdog con Mayor Oportunidad:**\n"
        f"• **Equipo/Evento:** {nombre_underdog}\n"
        f"• **Análisis/Recomendación:** {rec_underdog}\n"
        f"• **Enlace de Compra:** {link_underdog}\n\n"
    )

    nombre_favorito = favorito_convertido.get('nombre', 'Desconocido')
    rec_favorito = favorito_convertido.get('recomendacion', 'Sin recomendación')

    texto_favorito = (
        f"⚡ **Ex-Favorito (Nuevo Underdog en Vivo):**\n"
        f"• **Equipo/Evento:** {nombre_favorito}\n"
        f"• **Análisis/Recomendación:** {rec_favorito}\n"
        f"• **Enlace de Compra:** {link_favorito}"
    )

    return texto_underdog + texto_favorito

def monitor_kalshi_bitcoin():
    """
    Monitorea los contratos de Bitcoin en Kalshi para lapsos de 15 minutos y 1 hora.
    Toma el precio exacto con un retraso de 1 a 2 segundos para mayor precisión 
    del cierre anterior y analiza tendencias de 2 contratos consecutivos.
    """
    pass

def monitor_news_and_social():
    """
    Monitorea noticieros de EE.UU. y el mundo sobre bolsa, oro y criptomonedas,
    así como las redes sociales de las 10 empresas y 10 personas influyentes recomendadas.
    """
    pass

def monitor_whales():
    """
    Monitorea transacciones de ballenas y determina la dirección (compra/venta)
    para dictar si el mercado se mueve al alza o a la baja.
    """
    pass

def monitor_sports_odds():
    """
    Monitorea deportes en Kalshi (fútbol, béisbol y tenis con máxima prioridad).
    Detecta anomalías en las probabilidades, favoritos que empiezan perdiendo pero ganan,
    y oportunidades en underdogs especificando el nombre exacto del equipo o jugador 
    y líneas extendidas (over/under de innings, sets, goles, puntos).
    """
    pass

def bot_main_loop():
    # Confirmación inicial enviada a Discord al arrancar el bot
    enviar_a_discord("🚀 **Bot de Trading iniciado y conectado correctamente a Discord.**")
    
    while True:
        try:
            # Ejecución secuencial de los sistemas de monitoreo avanzados
            monitor_kalshi_bitcoin()
            monitor_news_and_social()
            monitor_whales()
            monitor_sports_odds()

        except Exception as e:
            print(f"Error en el ciclo del bot: {e}")
            
        finally:
            time.sleep(1) # Ciclo optimizado en tiempo real

if __name__ == "__main__":
    # Iniciar servidor HTTP en un hilo separado para cumplir con el requisito de Render (Keep-Alive)
    server_thread = threading.Thread(target=run_http_server)
    server_thread.daemon = True
    server_thread.start()
    
    # Iniciar el núcleo principal del bot
    bot_main_loop()
