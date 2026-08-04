import asyncio
import json
import requests
import websockets
from datetime import datetime, timedelta

# ==========================================
# CONFIGURACIÓN Y PARÁMETROS GLOBALES
# ==========================================
# Reemplaza la siguiente cadena con tu NUEVA URL de Webhook de Discord
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1534228345645039680/OP6raerP1RlkCl6WJvJ_Vto9FSJ05i42xOtRDbhHY-6KPv3Wlmgg9yatZEb-gqmiXbsz"
COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"

# Estrategia y Filtros
VOLUMEN_BALLENA_MIN = 5.0  # BTC
CIERRES_HISTORIAL_MAX = 10
FILTRO_VOLATILIDAD_1H_PCT = 1.5  # Porcentaje de cambio máximo permitido en 1h

# Gestión de Riesgo (Fase Beta $100 USD)
CAPITAL_INICIAL = 100.0
META_CAPITAL = 200.0
APUESTA_BASE = 2.50
STOP_LOSS_DIARIO = -12.00
SECUENCIA_RECUPERACION = [2.50, 4.00, 6.50]

# Control de Estado en Memoria
cierres_15m = []            # Guarda historial de cierres ("VERDE" / "ROJO")
precios_1h = []             # Historial de precios para cálculo de volatilidad
bloqueo_noticias_hasta = None  # Timestamp de enfriamiento por noticias


# ==========================================
# MÓDULO DE NOTIFICACIONES DISCORD
# ==========================================
def enviar_alerta_discord(mensaje):
    payload = {
        "content": mensaje,
        "username": "Bot Kalshi 15M"
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        print(f"Respuesta Discord BTC - Status Code: {response.status_code}")
        if response.status_code not in [200, 204]:
            print(f"Error enviando webhook (Status: {response.status_code}): {response.text}")
    except Exception as e:
        print(f"Error de conexión al enviar notificación: {e}")


# ==========================================
# FILTROS Y GESTIÓN DE RIESGO
# ==========================================
def activar_enfriamiento_noticias(minutos=15, motivo="Noticia de Alto Impacto"):
    """Bloquea entradas por un periodo de enfriamiento tras eventos o noticias."""
    global bloqueo_noticias_hasta
    bloqueo_noticias_hasta = datetime.now() + timedelta(minutes=minutos)
    alerta = f"🛑 **FILTRO DE NOTICIAS ACTIVADO**: Enfriamiento por {minutos}m ({motivo}). No se emitirán entradas."
    enviar_alerta_discord(alerta)

def esta_en_enfriamiento():
    """Verifica si el bot está en periodo de enfriamiento por noticias."""
    if bloqueo_noticias_hasta and datetime.now() < bloqueo_noticias_hasta:
        return True
    return False

def evaluar_volatilidad_1h(precio_actual):
    """Calcula el rango de volatilidad de la última hora."""
    precios_1h.append((datetime.now(), precio_actual))
    
    # Limpiar precios mayores a 1 hora
    hace_una_hora = datetime.now() - timedelta(hours=1)
    while precios_1h and precios_1h[0][0] < hace_una_hora:
        precios_1h.pop(0)

    if len(precios_1h) < 2:
        return True  # Datos insuficientes aún

    precios_vals = [p[1] for p in precios_1h]
    min_p = min(precios_vals)
    max_p = max(precios_vals)
    variacion_pct = ((max_p - min_p) / min_p) * 100

    if variacion_pct > FILTRO_VOLATILIDAD_1H_PCT:
        return False  # Volatilidad excesiva
    return True


# ==========================================
# LÓGICA OPERATIVA (GATILLO 15M)
# ==========================================
def evaluar_racha_15m():
    """Evalúa si existen al menos 2 cierres seguidos en la misma dirección."""
    if len(cierres_15m) < 2:
        return None
    
    if cierres_15m[-1] == cierres_15m[-2]:
        return cierres_15m[-1]
    return None

def registrar_cierre_vela(cierre_color, minuto_actual, precio_actual):
    """Procesa el cierre de una vela de 15m y valida las condiciones de entrada."""
    cierres_15m.append(cierre_color)
    if len(cierres_15m) > CIERRES_HISTORIAL_MAX:
        cierres_15m.pop(0)

    # Validar filtros antes de emitir alerta
    if esta_en_enfriamiento():
        print("Entrada omitida: Bot en enfriamiento por noticias.")
        return

    if not evaluar_volatilidad_1h(precio_actual):
        alerta_vol = f"⚠️ **ENTRADA OMITIDA**: Volatilidad en 1h supera el {FILTRO_VOLATILIDAD_1H_PCT}%."
        enviar_alerta_discord(alerta_vol)
        return

    racha = evaluar_racha_15m()
    
    # Condición principal: Minutos 1 a 4 y racha confirmada (≥2 cierres)
    if racha and (1 <= minuto_actual <= 4):
        emoji = "🟢" if racha == "VERDE" else "🔴"
        alerta = (
            f"🚨 **ALERTA KALSHI 15M**: Racha Confirmada ({racha} {emoji})\n"
            f"⏱ **Ventana**: Minuto {minuto_actual}\n"
            f"🎯 **Target Precio Contrato**: $0.30 - $0.35 USD\n"
            f"💰 **Gestión**: Apuesta Base $2.50 (Recuperación: 2.50 -> 4.00 -> 6.50)\n"
            f"🛑 **Stop-Loss Diario**: -$12.00 USD"
        )
        enviar_alerta_discord(alerta)


# ==========================================
# WEBSOCKET COINBASE (TIEMPO REAL)
# ==========================================
async def procesar_websocket():
    suscripcion = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["matches"]
    }

    while True:
        try:
            async with websockets.connect(COINBASE_WS_URL) as ws:
                await ws.send(json.dumps(suscripcion))
                print("Conectado a WebSocket de Coinbase Exchange...")

                while True:
                    mensaje = await ws.recv()
                    data = json.loads(mensaje)

                    if data.get("type") == "match":
                        tamano_btc = float(data.get("size", 0))
                        precio = float(data.get("price", 0))
                        side = data.get("side")

                        # Registro de precio para volatilidad 1h
                        evaluar_volatilidad_1h(precio)

                        # Detección de Ballenas (> 5 BTC)
                        if tamano_btc >= VOLUMEN_BALLENA_MIN:
                            tipo_operacion = "COMPRA" if side == "buy" else "VENTA"
                            emoji = "🐋🟢" if side == "buy" else "🐋🔴"
                            alerta_ballena = (
                                f"{emoji} **MOVIMIENTO DE BALLENA DETECTADO**\n"
                                f"**Monto**: {tamano_btc:.2f} BTC (~${tamano_btc * precio:,.2f} USD)\n"
                                f"**Tipo**: {tipo_operacion} a ${precio:,.2f}"
                            )
                            enviar_alerta_discord(alerta_ballena)

        except Exception as e:
            print(f"Conexión perdida con WebSocket: {e}. Reconectando en 5 segundos...")
            await asyncio.sleep(5)


# ==========================================
# PUNTO DE ENTRADA
# ==========================================
if __name__ == "__main__":
    enviar_alerta_discord("🤖 **Bot Kalshi 15M desplegado correctamente.**")
    asyncio.run(procesar_websocket())
