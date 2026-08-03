async def coinbase_websocket_listener():
    global volatility_pause, price_history
    ws_url = "wss://ws-feed.exchange.coinbase.com"

    subscribe_message = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["matches"]
    }

    while True:
        try:
            async for websocket in websockets.connect(ws_url):
                await websocket.send(json.dumps(subscribe_message))
                await send_discord_alert("🟢 **WebSocket de Coinbase conectado con éxito.**", title="System Status")

                async for message in websocket:
                    data = json.loads(message)
                    if data.get("type") == "match":
                        price = float(data["price"])
                        size = float(data["size"])
                        side = data["side"]

                        # Historial reciente
                        price_history.append(price)
                        if len(price_history) > 20:
                            price_history.pop(0)

                        # 1. Detección de Ballenas
                        if size >= WHALE_THRESHOLD_BTC:
                            msg = (
                                f"🐋 **Movimiento de Ballena Detectado**\n"
                                f"• **Monto:** {size:.2f} BTC\n"
                                f"• **Tipo:** {side.upper()}\n"
                                f"• **Precio:** ${price:.2f}"
                            )
                            await send_discord_alert(msg, title="Whale Alert")

                        # 2. Filtro de Volatilidad
                        if check_volatility_filter(price_history):
                            if not volatility_pause:
                                volatility_pause = True
                                await send_discord_alert("⚡ **Alta volatilidad/reversiones detectadas.** Pausando...", title="System Status")
                        else:
                            volatility_pause = False

                        # 3. Trailing Stop
                        manage_trailing_stop(price)

                        # 4. Evaluación de Entrada
                        if is_within_entry_window() and not active_position and not volatility_pause:
                            signal = check_racha_signal(consecutive_closes)
                            if signal != "NEUTRAL":
                                await execute_kalshi_trade(signal, price)

        except websockets.ConnectionClosed:
            await send_discord_alert("⚠️ **Conexión perdida con Coinbase. Reconectando...**", title="System Status")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Error en WebSocket: {e}")
            await asyncio.sleep(5)
