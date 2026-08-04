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

# URL de respaldo general de Kalshi y Webhook de Discord (puedes configurar tu Webhook como variable de entorno en Render)
URL_KALSHI_DEFAULT = "https://kalshi.com"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "TU_WEBHOOK_DE_DISCORD_AQUI")

def enviar_a_discord(mensaje):
    """
    Envía la alerta formateada directamente a tu canal de Discord mediante Webhook.
    """
    if "TU_WEBHOOK_DE_DISCORD" in DISCORD_WEBHOOK_URL:
        print(">>> [AVISO] Webhook de Discord no configurado. La alerta solo se imprime en consola.")
        return

    payload = {"content": mensaje}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if response.status_code != 204 and response.status_code != 200:
            print(f"Error al enviar a Discord: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Excepción al conectar con Discord: {e}")

def generar_mensaje_apuestas(underdog_realista, favorito_convertido):
    # Obtener el enlace específico del evento o usar la página principal si no está disponible
    url_underdog = underdog_realista.get('enlace', URL_KALSHI_DEFAULT)
    nombre_underdog = underdog_realista.get('nombre', 'Desconocido')
    rec_underdog = underdog_realista.get('recomendacion', 'Sin recomendación')
    motivo_underdog = underdog_realista.get('motivo', 'Anomalía detectada en probabilidades')
    linea_underdog = underdog_realista.get('linea', 'Más de 2.5 sets / Línea extendida')

    texto_underdog = (
        f"🔥 **[SPORTS] UNDERDOG CON MAYOR OPORTUNIDAD:**\n"
        f"• **Evento:** {nombre_underdog}\n"
        f"• **Análisis/Recomendación:** {rec_underdog}\n"
        f"• **Motivo:** {motivo_underdog}\n"
        f"• **Línea:** {linea_underdog}\n"
        f"• **Enlace Exacto del Juego:** {url_underdog}\n\n"
    )

    url_favorito = favorito_convertido.get('enlace', URL_KALSHI_DEFAULT)
    nombre_favorito = favorito_convertido.get('nombre', 'Desconocido')
    rec_favorito = favorito_convertido.get('recomendacion', 'Sin recomendación')
    motivo_favorito = favorito_convertido.get('motivo', 'El favorito comenzó perdiendo pero hay probabilidad realista de remontada.')
    linea_favorito = favorito_convertido.get('linea', 'Más de 2.5 sets (Cuota con valor para Scalping).')

    texto_favorito = (
        f"⚡ **[SPORTS] EX-FAVORITO / NUEVO UNDERDOG EN VIVO:**\n"
        f"• **Evento:** {nombre_favorito}\n"
        f"• **Análisis/Recomendación:** {rec_favorito}\n"
        f"• **Motivo:** {motivo_favorito}\n"
        f"• **Línea:** {linea_favorito}\n"
        f"• **Enlace Exacto del Juego:** {url_favorito}"
    )

    mensaje_final = texto_underdog + texto_favorito
    return mensaje_final

def monitor_kalshi_bitcoin():
    """
    Monitorea los contratos de Bitcoin en Kalshi para lapsos de 15 minutos y 1 hora.
    """
    pass

def monitor_news_and_social():
    """
    Monitorea noticieros y redes sociales.
    """
    pass

def monitor_whales():
    """
    Monitorea transacciones de ballenas.
    """
    pass

def monitor_sports_odds():
    """
    Monitorea todos los deportes en Kalshi y emite alertas detalladas.
    """
    # Datos de prueba con enlaces específicos simulados (puedes enlazar la URL exacta del mercado de Kalshi aquí)
    underdog_prueba = {
        'nombre': 'WTA Tenis - Sakkari vs Pegula (En Vivo - Set 2)',
        'recomendacion': 'Comprar SÍ al Underdog: Maria Sakkari',
        'motivo': 'El favorito comenzó perdiendo el primer set pero hay probabilidad realista de remontada.',
        'linea': 'Más de 2.5 sets (Cuota con valor para Scalping).',
        'enlace': 'https://kalshi.com' # Aquí puedes poner la ruta exacta del mercado cuando esté disponible
    }
    
    favorito_prueba = {
        'nombre': 'WTA Tenis - Sakkari vs Pegula (En Vivo - Set 2)',
        'recomendacion': 'Comprar SÍ al Underdog: Maria Sakkari',
        'motivo': 'El favorito comenzó perdiendo el primer set pero hay probabilidad realista de remontada.',
        'linea': 'Más de 2.5 sets (Cuota con valor para Scalping).',
        'enlace': 'https://kalshi.com' # Aquí puedes poner la ruta exacta del mercado cuando esté disponible
    }
    
    alerta = generar_mensaje_apuestas(underdog_prueba, favorito_prueba)
    
    # Imprimir en consola de Render
    print("\n----------------------------------------")
    print(alerta)
    print("----------------------------------------\n")
    
    # Enviar la notificación a Discord
    enviar_a_discord(alerta)

def bot_main_loop():
    print(">>> Núcleo del bot de señales iniciado correctamente.")
    while True:
        try:
            # Ejecución secuencial de los sistemas de monitoreo avanzados
            monitor_kalshi_bitcoin()
            monitor_news_and_social()
            monitor_whales()
            monitor_sports_odds()
            
        except Exception as e:
            print(f"Error en el ciclo del bot: {e}")
            
        time.sleep(15) # Ciclo de pausa entre revisiones

if __name__ == "__main__":
    # Iniciar servidor HTTP en un hilo separado para cumplir con el requisito de Render (Keep-Alive)
    server_thread = threading.Thread(target=run_http_server)
    server_thread.daemon = True
    server_thread.start()
    
    # Iniciar el núcleo principal del bot de forma concurrente
    bot_thread = threading.Thread(target=bot_main_loop)
    bot_thread.daemon = True
    bot_thread.start()

    # Mantener vivo el hilo principal
    while True:
        time.sleep(10)
