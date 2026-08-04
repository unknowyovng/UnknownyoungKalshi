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
            # 1. Monitoreo de Bitcoin, criptoactivos y tendencias (Alcista/Bajista)
            # 2. Monitoreo de rachas de mercado en Kalshi
            # 3. Monitoreo instantáneo de compras/ventas grandes en Bitcoin
            # (con recomendación de comprar o vender basada en el movimiento)
            
            # Simulación de detección de orden grande
            orden_grande_detectada = True
            if orden_grande_detectada:
                direccion = "ARRIBA" # o ABAJO
                mensaje = f"¡ALERTA MOVIMIENTO GRANDE EN BITCOIN!\nEl mercado Kalshi se moverá más de $100.\nSe recomienda comprar: {direccion}"
                requests.post(WEBHOOK_URL, json={"content": mensaje})

            # 4. Monitoreo de deportes: Tennis (ATP, WTA, ITF), Soccer y Baseball
            # 5. Detección de Underdog y enlaces específicos
            # 6. Monitoreo de noticias de las 10 personas más relevantes y empresas
            # 7. Monitoreo de movimientos y compras/ventas de ballenas

        except Exception as e:
            print(f"Error en el monitoreo: {e}")
        time.sleep(60)


if __name__ == "__main__":
    bot_thread = threading.Thread(target=monitorear_mercados, daemon=True)
    bot_thread.start()
    app.run(host="0.0.0.0", port=10000)
