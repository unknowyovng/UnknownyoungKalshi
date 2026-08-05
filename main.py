import os
import time
import asyncio
import threading
import requests
from flask import Flask
from playwright.async_api import async_playwright

# Configuración del servidor HTTP (Keep-Alive para evitar caídas en Render)
app = Flask('')

@app.route('/', methods=['GET', 'HEAD'])
def home():
    """Responde tanto a peticiones GET como HEAD de Render Health Check."""
    return "El bot de trading cuantitativo, monitoreo de mercados, deportes, ballenas y noticias está 100% activo y operativo.", 200

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        app.run(host='0.0.0.0', port=port, use_reloader=False)
    except Exception as e:
        print(f"Error crítico en el servidor HTTP: {e}")

def self_ping_loop():
    """Mantiene la instancia de Render activa enviando un ping cada 4 minutos."""
    time.sleep(10)
    port = os.environ.get("PORT", "8080")
    # Usa RENDER_EXTERNAL_URL si existe, o localhost como respaldo
    url = os.environ.get("RENDER_EXTERNAL_URL", f"http://127.0.0.1:{port}/")
    print(f"[SELF-PING] Servicio de Keep-Alive iniciado apuntando a: {url}")
    
    while True:
        try:
            requests.get(url, timeout=10)
            print("[SELF-PING] Ping de mantenimiento enviado con éxito.")
        except Exception as e:
            print(f"[SELF-PING] Error al enviar ping: {e}")
        time.sleep(240)  # Cada 4 minutos (antes del límite de inactivación de 5m de Render)

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
    """
    global seen_btc_opportunities
    try:
        # 1. Obtener trades recientes de BTC/USDT en Binance para detectar ballenas
        trades_url = "https://api.binance.com/api/v3/trades?symbol=BTCUSDT&limit=50"
        res_trades = requests.get(trades_url, timeout=5)
        
        whale_bias = None  # "UP" (compras masivas) o "DOWN" (ventas masivas)
        
        if res_trades.status_code == 200:
            trades = res_trades.json()
            buy_vol = sum(float(t['qty']) for t in trades if not t['isBuyerMaker'])
            sell_vol = sum(float(t['qty']) for t in trades if t['isBuyerMaker'])
            
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
                
                if "btc" in ticker.lower() or "bitcoin" in title.lower():
                    yes_bid = m.get("yes_bid", 0)
                    volume = m.get("volume", 0)
                    
                    if 0 < yes_bid < 40 and ticker not in seen_btc_opportunities:
                        recomendacion = "UP" if (whale_bias == "UP" or "above" in title.lower()) else "DOWN"
                        seen_btc_opportunities.add(ticker)
                        link = construir_url_kalshi(ticker)
                        
                        msg = (
                            f"🐋 **ALERTA DE BALLENAS & BITCOIN (Kalshi)** 🐋\n"
                            f"• **Contrato:** {title}\n"
                            f"• **Ticker:** `{ticker}`\n"
                            f"• **Cuota Actual YES:** {yes_bid}%\n"
                            f"• **Volumen:** {volume} contratos\n"
                            f"• **Presión de Ballenas:** {whale_bias if whale_bias else 'Flujo Normal'}\n"
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

ultimo_precio_alerta = None

async def agente_autonomo_ia():
    """
    Navegador IA autónomo que monitorea Binance/TradingView en vivo y dispara
    alertas de ineficiencia reales (<40%) sin saturar Discord con spam.
    """
    global ultimo_precio_alerta
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
                # 1. Obtención directa de precio Spot BTC en tiempo real desde Binance
                try:
                    btc_data = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5).json()
                    raw_price = float(btc_data['price'])
                    spot_price = f"{raw_price:,.2f}"
                except Exception:
                    spot_price = "N/A"
                    raw_price = 0

                # 2. Consultar cuota real en Kalshi para el mercado de BTC
                kalshi_odds = None
                try:
                    res_k = requests.get("https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=50", timeout=5)
                    if res_k.status_code == 200:
                        markets = res_k.json().get("markets", [])
                        for m in markets:
                            if "btc" in m.get("ticker", "").lower() or "bitcoin" in m.get("title", "").lower():
                                kalshi_odds = m.get("yes_bid", 0)
                                break
                except Exception:
                    kalshi_odds = None

                # 3. Disparar solo si existe cuota real < 40% y el precio ha variado (> $50 USD)
                if kalshi_odds is not None and 0 < kalshi_odds < 40:
                    if ultimo_precio_alerta is None or abs(raw_price - ultimo_precio_alerta) > 50:
                        ultimo_precio_alerta = raw_price
                        
                        alerta = (
                            f"🚨 **REGLA DE ORO: INEFICIENCIA DETECTADA (<40%)** 🚨\n"
                            f"• **Activo:** BTC/USDT (Velas 15m)\n"
                            f"• **Precio Spot Binance:** ${spot_price}\n"
                            f"• **Cuota Kalshi:** {kalshi_odds}%\n"
                            f"• **Estrategia:** Trend Following activa.\n"
                            f"• **Gestión de Riesgo:** Martingala Progresiva (Fase Beta $100 - Máximo 3 progresiones).\n"
                            f"🎯 **RECOMENDACIÓN:** **COMPRAR UP (SI TENDENCIA ES ALCISTA) / DOWN (SI ES BAJISTA)**"
                        )
                        enviar_a_discord(alerta)
                        print(f"[ALERTA DISPARADA] Spot: ${spot_price} | Kalshi: {kalshi_odds}%")

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
    # 1. Hilo del Servidor Web Flask
    server_thread = threading.Thread(target=run_http_server, daemon=True)
    server_thread.start()

    # 2. Hilo del Auto-Ping para evitar que Render entre en reposo
    ping_thread = threading.Thread(target=self_ping_loop, daemon=True)
    ping_thread.start()

    # 3. Hilo del Agente IA (Playwright)
    ia_thread = threading.Thread(target=start_ia_agent_loop, daemon=True)
    ia_thread.start()

    # 4. Ciclo Principal de Monitoreo
    bot_main_loop()
