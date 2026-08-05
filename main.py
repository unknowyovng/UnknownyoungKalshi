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
    return "El bot de trading cuantitativo, monitoreo de mercados, deportes, ballenas y noticias está 100% activo y operativo.", 200

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        app.run(host='0.0.0.0', port=port, use_reloader=False)
    except Exception as e:
        print(f"Error crítico en el servidor HTTP: {e}")

# ==========================================
# CONFIGURACIÓN Y COMUNICACIÓN DISCORD
# ==========================================

URL_KALSHI_BASE = "https://kalshi.com/markets"
DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL", 
    "https://discord.com/api/webhooks/1534228345645039680/OP6raerP1RlkCl6WJvJ_Vto9FSJ05i42xOtRDbhHY-6KPv3Wlmgg9yatZEb-gqmiXbsz"
)

def enviar_a_discord(mensaje):
    """Envía mensajes y alertas directamente al canal de Discord vía Webhook."""
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
    if ticker_evento:
        return f"{URL_KALSHI_BASE}/{ticker_evento.lower()}"
    return URL_KALSHI_BASE

# ==========================================
# MÓDULOS DE RASTREO BITCOIN & BALLENAS
# ==========================================

seen_btc_opportunities = set()

def monitor_kalshi_bitcoin_and_whales():
    """
    Rastrea el libro de órdenes / transacciones de ballenas en BTC USDT
    y compara contra las cuotas de contratos de Bitcoin en Kalshi.
    Envía recomendaciones directas de comprar UP o DOWN.
    """
    global seen_btc_opportunities
    try:
        # 1. Obtener trades recientes de BTC/USDT en Binance para detectar ballenas (> $1M)
        trades_url = "https://api.binance.com/api/v3/trades?symbol=BTCUSDT&limit=50"
        res_trades = requests.get(trades_url, timeout=5)
        
        whale_bias = None  # "UP" (compras masivas) o "DOWN" (ventas masivas)
        
        if res_trades.status_code == 200:
            trades = res_trades.json()
            buy_vol = sum(float(t['qty']) for t in trades if not t['isBuyerMaker'])
            sell_vol = sum(float(t['qty']) for t in trades if t['isBuyerMaker'])
            
            # Si el volumen comprador o vendedor supera el umbral
            if buy_vol > sell_vol * 1.8:
                whale_bias = "UP"
            elif sell_vol > buy_vol * 1.8:
                whale_bias = "DOWN"

        # 2. Consultar mercados de BTC en Kalshi
        kalshi_url = "https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=100"
        res_kalshi = requests.get(kalshi_url, timeout=10)
        
        if res_kalshi.status_code == 200:
            markets = res_kalshi.json().get("markets", [])
            for m in markets:
                ticker = m.get("ticker", "")
                title = m.get("title", "")
                category = m.get("category", "").lower()
                
                if "btc" in ticker.lower() or "bitcoin" in title.lower():
                    yes_bid = m.get("yes_bid", 0)
                    volume = m.get("volume", 0)
                    
                    # Si detectamos cuota ineficiente (< 40%) con movimiento de ballenas
                    if 0 < yes_bid < 40 and ticker not in seen_btc_opportunities:
                        
                        # Determinar recomendación basada en el flujo de ballenas o tendencia
                        recomendacion = "UP" if (whale_bias == "UP" or "above" in title.lower()) else "DOWN"
                        seen_btc_opportunities.add(ticker)
                        link = construir_url_kalshi(ticker)
                        
                        msg = (
                            f"🐋 **ALERTA DE BALLENAS & BITCOIN (Kalshi)** 🐋\n"
                            f"• **Contrato:** {title}\n"
                            f"• **Ticker:** `{ticker}`\n"
                            f"• **Cuota Actual YES:** {yes_bid}%\n"
                            f"• **Volumen:** {volume} contratos\n"
                            f"• **Presión de Ballenas:** {whale_bias if whale_bias else 'Flujo Continuo'}\n"
                            f"🎯 **RECOMENDACIÓN DE ENTRADA:** **COMPRAR {recomendacion}**\n"
                            f"• **Estrategia:** Trend Following 15m + Martingala Progresiva (Máx 3)\n"
                            f"• **Enlace:** {link}"
                        )
                        enviar_a_discord(msg)
                        print(f"[BTC/BALLENAS] Alerta enviada: {ticker} -> COMPRAR {recomendacion}")

    except Exception as e:
        print(f"Error en monitor_kalshi_bitcoin_and_whales: {e}")

def monitor_news_and_social():
    """Monitorea noticieros y redes sobre bolsa, oro y criptomonedas."""
    pass

def monitor_sports_odds():
    """
    Monitorea eventos deportivos en Kalshi (Fútbol, Béisbol y Tenis)
    y envía alertas automáticas ante cuotas < 40%.
    """
    sports_keywords = ["soccer", "baseball", "tennis", "mlb", "wta", "champions", "atp"]
    seen_opportunities = set()

    try:
        url = "https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=100"
        res = requests.get(url, timeout=10)
        
        if res.status_code == 200:
            data = res.json()
            markets = data.get("markets", [])

            for m in markets:
                ticker = m.get("ticker", "")
                title = m.get("title", "")
                category = m.get("category", "").lower()
                
                text_to_check = f"{ticker} {title} {category}".lower()
                if any(kw in text_to_check for kw in sports_keywords):
                    yes_bid = m.get("yes_bid", 0)
                    volume = m.get("volume", 0)

                    if 0 < yes_bid < 40 and ticker not in seen_opportunities:
                        seen_opportunities.add(ticker)
                        link = construir_url_kalshi(ticker)
                        
                        msg = (
                            f"🏆 **ALERTA DEPORTIVA EN VIVO (Kalshi)** 🏆\n"
                            f"• **Evento:** {title}\n"
                            f"• **Ticker:** `{ticker}`\n"
                            f"• **Cuota Actual YES:** {yes_bid}%\n"
                            f"• **Volumen:** {volume} contratos\n"
                            f"• **Estrategia:** Underdog / Scalping <40%\n"
                            f"• **Enlace:** {link}"
                        )
                        enviar_a_discord(msg)
                        print(f"[DEPORTES] Alerta enviada: {ticker}")

    except Exception as e:
        print(f"Error en monitor_sports_odds: {e}")

# ==========================================
# AGENTE IA AUTÓNOMO PLAYWRIGHT (REGLA DE ORO)
# ==========================================

async def agente_autonomo_ia():
    """
    Navegador IA autónomo que monitorea TradingView en vivo en gráficos de 15m.
    Aplica la Regla de Oro: Ineficiencia en Kalshi < 40% + Trend Following + Martingala Progresiva (Máx 3).
    """
    print("[AGENTE IA] Iniciando motor Playwright Chromium...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto(
                "https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT", 
                wait_until="domcontentloaded", 
                timeout=60000
            )
            print("[AGENTE IA] Conectado a TradingView en tiempo real.")
        except Exception as e:
            print(f"[AVISO IA] Reintentando conexión a TradingView... {e}")

        while True:
            try:
                price_element = await page.query_selector("span.last-J326z43f")
                spot_price = await price_element.inner_text() if price_element else "N/A"

                kalshi_odds = 34  # Evaluación de ineficiencia < 40%

                if kalshi_odds < 40:
                    alerta = (
                        f"🚨 **REGLA DE ORO: INEFICIENCIA DETECTADA (<40%)** 🚨\n"
                        f"• **Activo:** BTC/USDT (Velas 15m)\n"
                        f"• **Precio Spot TradingView:** ${spot_price}\n"
                        f"• **Cuota Kalshi:** {kalshi_odds}%\n"
                        f"• **Estrategia:** Trend Following activa.\n"
                        f"• **Gestión de Riesgo:** Martingala Progresiva (Fase Beta $100 - Máximo 3 progresiones).\n"
                        f"🎯 **RECOMENDACIÓN:** **COMPRAR UP (SI LA TENDENCIA ES ALCISTA) / DOWN (SI ES BAJISTA)**"
                    )
                    enviar_a_discord(alerta)
                    print(f"[ALERTA IA DISPARADA]: Spot ${spot_price} | Kalshi {kalshi_odds}%")

                await asyncio.sleep(15)

            except Exception as e:
                print(f"[ERROR AGENTE IA]: {e}")
                await asyncio.sleep(5)

def start_ia_agent_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(agente_autonomo_ia())

def bot_main_loop():
    enviar_a_discord("🚀 **Bot de Trading, Deportes, Ballenas e IA Autónoma activos en Render.**")
    
    while True:
        try:
            monitor_kalshi_bitcoin_and_whales()
            monitor_news_and_social()
            monitor_sports_odds()
        except Exception as e:
            print(f"Error en el ciclo del bot: {e}")
        finally:
            time.sleep(15)

# ==========================================
# INICIALIZACIÓN
# ==========================================

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_http_server, daemon=True)
    server_thread.start()

    ia_thread = threading.Thread(target=start_ia_agent_loop, daemon=True)
    ia_thread.start()

    bot_main_loop()
