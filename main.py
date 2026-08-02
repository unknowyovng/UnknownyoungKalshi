print(f"[{t_stamp}] BTC Kalshi: ${close_p:,.2f} | ACCIÓN: {action} ({reason})", flush=True)

                                if "COMPRAR" in action or "CERRAR" in action or "PROFIT" in action:
                                    if action != last_sent_action:
                                        send_discord_alert(action, close_p, reason, t_stamp)
                                        last_sent_action = action

                                current_minute_ticks = []
                            
                            last_minute = now.minute

        except Exception as e:
            print(f"[RECONECTANDO COINBASE]: {e}", flush=True)
            await asyncio.sleep(5)

def run_bot():
    load_initial_candles()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coinbase_websocket_listener())

if __name__ == "__main__":
    # Iniciar el bot en un hilo secundario con su propio event loop
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Iniciar el servidor Flask en el hilo principal
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
