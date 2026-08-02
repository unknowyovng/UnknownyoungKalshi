# ==========================================
# 4. TAREA DE ANÁLISIS Y ENVIÓ DE SEÑALES
# ==========================================
async def ciclo_monitoreo():
    await bot.wait_until_ready()
    
    # Busca automáticamente el canal por su nombre
    canal = discord.utils.get(bot.get_all_channels(), name="alertas-kalshi")

    while not bot.is_closed():
        try:
            if canal:
                # -----------------------------------------------------------
                # AQUÍ LÓGICA DE MONITOREO Y SEÑALES
                # -----------------------------------------------------------
                precio_btc = 63468.01
                global manual_target, modo_manual
                target_calculado_auto = 63456.97
                target_activo = manual_target if modo_manual and manual_target else target_calculado_auto

                # Imprime en la consola de Render para verificar que está escaneando
                print(f"🔍 Monitoreando... BTC: {precio_btc} | Target Activo: {target_activo}")
            else:
                print("⚠️ No se encontró el canal 'alertas-kalshi'")

        except Exception as e:
            print(f"⚠️ Error en monitoreo: {e}")

        # Frecuencia de escaneo (cada 15 segundos)
        await asyncio.sleep(15)
