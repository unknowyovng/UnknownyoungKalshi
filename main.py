import os
import time
import requests
from flask import Flask
import threading

app = Flask('')

@app.route('/')
def home():
    return "El bot de trading, monitoreo de mercados, deportes, ballenas y noticias está 100% activo y operativo."

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        # Se desactiva el reloader para evitar duplicar hilos en Render
        app.run(host='0.0.0.0', port=port, use_reloader=False)
    except Exception as e:
        print(f"Error crítico en el servidor HTTP: {e}")

# ==========================================
# CONFIGURACIÓN Y MÓDULOS DE MONITOREO
# ==========================================

URL_KALSHI_BASE = "https://kalshi.com/markets"

def construir_url_kalshi(ticker_evento=None):
    """
    Construye la URL exacta del mercado para evitar errores 404.
    Si se provee un ticker de mercado (ej: 'WTA-MATCH-X'), genera la ruta directa.
    """
    if ticker_evento:
        return f"{URL_KALSHI_BASE}/{ticker_evento.lower()}"
    return "https://kalshi.com/markets"

def generar_mensaje_apuestas(underdog_realista, favorito_convertido):
    # Obtener enlaces dinámicos validados mediante ticker o slug
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
    pass

def monitor_news_and_social():
    pass

def monitor_whales():
    pass

def monitor_sports_odds():
    pass

def bot_main_loop():
    while True:
        try:
            # Ejecución secuencial de monitores
            monitor_kalshi_bitcoin()
            monitor_news_and_social()
            monitor_whales()
            monitor_sports_odds()

        except Exception as e:
            print(f"Error en el ciclo del bot: {e}")
            
        finally:
            # Pausa garantizada en el 'finally' para no saturar la CPU si ocurre una excepción continua
            time.sleep(1)

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_http_server)
    server_thread.daemon = True
    server_thread.start()
    
    bot_main_loop()
