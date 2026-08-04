import threading
import time
import requests
from flask import Flask

app = Flask(__name__)
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
WEBHOOK_URL = "https://discord.com/api/webhooks/1533349076593283252/QPKKfcqt0F1I0WcUEnwI5GjVsQTQYL23BvX8F0YM1p4laseCH0iDNPhdfd0VApHafggJ"


@app.route("/", methods=["GET", "HEAD"])
def index():
    return "OK", 200


def monitorear_mercados():
    while True:
        try:
            # 1. Monitoreo de Bitcoin y criptoactivos en Kalshi y Coinbase
            # 2. Monitoreo de deportes: Tennis (ATP, WTA, ITF), Soccer y Baseball

            underdog_detectado = True
            if underdog_detectado:
                nombre_underdog = "Melleiro"
                enlace_juego = "https://kalshi.com/markets/..."
                mensaje = f"¡ALERTA UNDERDOG!\nJugador: {nombre_underdog}\nEnlace: {enlace_juego}"
                requests.post(WEBHOOK_URL, json={"content": mensaje})

            # 3. Monitoreo de noticias de las 10 personas más relevantes y empresas
            # 4. Monitoreo de movimientos y compras/ventas de ballenas
            # 5. Monitoreo de compras o ventas en Bitcoin que muevan el mercado más de $100

        except Exception as e:
            print(f"Error en el monitoreo: {e}")
        time.sleep(60)


if __name__ == "__main__":
    bot_thread = threading.Thread(target=monitorear_mercados, daemon=True)
    bot_thread.start()
    app.run(host="0.0.0.0", port=10000)
