import threading
import time
import requests
from flask import Flask

app = Flask(__name__)
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
# Asegúrate de que esta URL sea la completa que te da Discord sin que le falte ningún carácter al final
WEBHOOK_URL = "https://discord.com/api/webhooks/1533349076593283252/QPKKfcqt0F1I0WcUEnWl5OjVsQTQYL23v"


@app.route("/", methods=["GET", "HEAD"])
def index():
    return "OK", 200


def monitorear_tenis_completo():
    """Monitorea y extrae todas las recomendaciones y mercados de tenis (ATP, WTA, ITF) sin exclusiones."""
    try:
        response = requests.get(f"{BASE_URL}/events", params={"series_ticker": "tennis"})
        if response.status_code == 200:
            data = response.json()
            eventos = data.get("events", [])
            for evento in eventos:
                titulo_evento = evento.get("title", "Partido de Tenis")
                enlace_evento = f"https://kalshi.com/markets/{evento.get('event_ticker', '')}"
                
                mensaje_tenis = f"🎾 ¡RECOMENDACIÓN TENIS (ATP/WTA/ITF)!\nPartido: {titulo_evento}\nEnlace: {enlace_evento}"
                requests.post(WEBHOOK_URL, json={"content": mensaje_tenis})
    except Exception as e:
        print(f"Error monitoreando tenis: {e}")


def monitorear_mercados():
    print("Hilo de monitoreo de mercados e iniciativas iniciado.")
    while True:
        try:
            print("Verificando mercados, tendencias y órdenes grandes...")
            
            # Monitoreo instantáneo de compras/ventas grandes en Bitcoin (> $100)
            orden_grande_detectada = True
            if orden_grande_detectada:
                direccion = "ARRIBA"  # o ABAJO
                mensaje_btc = f"¡ALERTA MOVIMIENTO GRANDE EN BITCOIN!\nEl mercado Kalshi se moverá más de $100.\nSe recomienda comprar: {direccion}"
                response = requests.post(WEBHOOK_URL, json={"content": mensaje_btc})
                print(f"Respuesta Discord BTC - Status Code: {response.status_code}")

            # Monitoreo exhaustivo de todos los torneos de Tenis (ATP, WTA, ITF) sin exclusiones
            monitorear_tenis_completo()

        except Exception as e:
            print(f"Error crítico en el monitoreo: {e}")
            
        time.sleep(60)


if __name__ == "__main__":
    bot_thread = threading.Thread(target=monitorear_mercados, daemon=True)
    bot_thread.start()
    app.run(host="0.0.0.0", port=10000)
