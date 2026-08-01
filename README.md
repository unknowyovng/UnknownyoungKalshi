import requests

def enviar_telegram(mensaje):
    TOKEN = "TU_BOT_TOKEN_TELEGRAM"
    CHAT_ID = "TU_CHAT_ID"
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?text={mensaje}&chat_id={CHAT_ID}"
    requests.get(url)
