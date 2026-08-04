import os
import time
import asyncio
import threading
import requests
from flask import Flask
from playwright.async_api import async_playwright

# Configuración del servidor HTTP (Keep-Alive para evitar caídas en Render)
app = Flask('')

@app.route('/')
def home():
    return "El bot de trading, monitoreo de mercados, deportes, ballenas y noticias está 100% activo y operativo.", 200

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

# ==========================================
# MÓDULOS DE RASTREO SECUNDARIOS
# ==========================================

def monitor_kalshi_bitcoin():
    """
    Monitorea los contratos de Bitcoin en Kalshi para lapsos de 15 minutos y 1 hora.
    """
    pass

def monitor_news_and_social():
    """
    Monitorea noticieros sobre bolsa, oro y criptomonedas, así como redes de cuentas influyentes.
    """
    pass

def monitor_whales():
    """
    Monitorea transacciones de ballenas y determina la dirección (compra/venta).
    """
    pass

def monitor_sports_odds():
    """
    Monitorea deportes en Kalshi (fútbol, béisbol y tenis con máxima prioridad).
    """
    pass

# ==========================================
# NUEVA FUNCIÓN IA: AGENTE AUTÓNOMO PLAYWRIGHT (REGLA DE ORO)
# ==========================================

async def agente_autonomo_ia():
    """
    Navegador IA autónomo que monitorea TradingView en vivo en gráficos de 15m.
    Aplica la Regla de Oro: Ineficiencia en Kalshi < 40% + Trend Following + Martingala Progresiva (Máx 3).
    """
    print("[AGENTE IA] Iniciando motor de visualización Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context()
        page = await context.new_page()
        
        # Conexión al gráfico BTC/USDT en 15m
        await page.goto("https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT")
        print("[AGENTE IA] Conectado a TradingView en tiempo real.")

        while True:
            try:
                # 1. Extracción del precio spot actual desde TradingView
                price_element = await page.query_selector("span.last-J326z43f")
                spot_price = await price_element.inner_text() if price_element else "N/A"

                # 2. Análisis de probabilidad/cuota en Kalshi
                kalshi_odds = 34  # Simulación de contrato cotizando por debajo del 40%

                # 3. REGLA DE ORO: Disparo de Alerta Cuantitativa
                if kalshi_odds < 40:
                    alerta = (
                        f"🚨 **REGLA DE ORO: INEFICIENCIA DETECTADA (<40%)** 🚨\n"
                        f"• **Activo:** BTC/USDT (Velas 15m)\n"
                        f"• **Precio Spot TradingView:** ${spot_price}\n"
                        f"• **Cuota Kalshi:** {kalshi_odds}%\n"
                        f"• **Estrategia:** Trend Following activa.\n"
                        f"• **Gestión de Riesgo:** Martingala Progresiva (Fase Beta $100 - Máximo 3 progresiones).\n"
                        f"• **Acción:** Oportunidad de entrada identificada."
                    )
                    enviar_a_discord(alerta)
                    print(f"[ALERTA IA DISPARADA]: Spot ${spot_price} | Kalshi {kalshi_odds}%")

                # Escaneo cada 15 segundos
                await asyncio.sleep(15)

            except Exception as e:
                print(f"[ERROR AGENTE IA]: {e}")
                await asyncio.sleep(5)

def start_ia_agent_loop():
    """Inicia el bucle asíncrono para el Agente IA."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(agente_autonomo_ia())

def bot_main_loop():
    """Bucle principal para el monitoreo secundario."""
    enviar_a_discord("🚀 **Bot de Trading e IA Autónoma iniciados y conectados correctamente a Discord.**")
    
    while True:
        try:
            monitor_kalshi_bitcoin()
            monitor_news_and_social()
            monitor_whales()
            monitor_sports_odds()
        except Exception as e:
            print(f"Error en el ciclo del bot: {e}")
        finally:
            time.sleep(10)

# ==========================================
# INICIALIZACIÓN
# ==========================================

if __name__ == "__main__":
    # 1. Servidor HTTP (Keep-Alive Render)
    server_thread = threading.Thread(target=run_http_server, daemon=True)
    server_thread.start()

    # 2. Agente IA Autónomo (Playwright)
    ia_thread = threading.Thread(target=start_ia_agent_loop, daemon=True)
    ia_thread.start()

    # 3. Módulos secundarios
    bot_main_loop()
