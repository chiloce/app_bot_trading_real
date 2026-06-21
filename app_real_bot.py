# =====================================================================
# MOTOR DE ESCANEO CONTINUO (BINGX)
# =====================================================================
if BOT_ENCENDIDO:
    PARES_A_REVISAR = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT", "XRP/USDT:USDT"]

    if st.session_state.en_operacion:
        try:
            # FORMATO CORREGIDO PARA LA CONSULTA DE POSICIONES ACTIVAS EN TESTNET
            par_activo = st.session_state.detalles_operacion.get("Par") + "/USDT:USDT"
            posiciones = exchange.fetch_positions(symbols=[par_activo])
            if posiciones and float(posiciones[0]['info'].get('positionAmt', 0)) == 0:
                st.session_state.en_operacion = False
                enviar_alerta(f"🏁 La posición en {st.session_state.detalles_operacion.get('Par')} ha sido cerrada.")
        except Exception as e:
            print(f"Error verificando estado en BingX: {e}")

    if st.session_state.en_operacion:
        df_op = pd.DataFrame([st.session_state.detalles_operacion])
        monitor_operacion.dataframe(df_op, use_container_width=True)
    else:
        monitor_operacion.info("Vigilando los pares en BingX... Esperando condiciones de mercado.")

    try:
        datos_consola = []
        for symbol in PARES_A_REVISAR:
            if st.session_state.en_operacion:
                break
                
            velas = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=2)
            if len(velas) < 2: continue
            
            vela_actual = velas[-1]
            precio_apertura = vela_actual[1]
            precio_actual = vela_actual[4]
            volumen_vela = vela_actual[5] * precio_actual
            
            variacion = ((precio_actual - precio_apertura) / precio_apertura) * 100
            
            datos_consola.append({
                "Moneda": symbol.split('/')[0],
                "Precio Actual": f"{precio_actual} USDT",
                "Variación Vela": f"{variacion:.3f}%",
                "Volumen": f"${volumen_vela:,.0f} USD"
            })
            
            if volumen_vela < VOLUMEN_MINIMO:
                continue
            
            direccion = None
            if variacion >= UMBRAL:
                direccion = "LONG"
            elif variacion <= -UMBRAL:
                direccion = "SHORT"

            if direccion and not st.session_state.en_operacion:
                if abrir_posicion_con_trailing(symbol, direccion, precio_actual):
                    st.session_state.en_operacion = True
                    st.rerun()
                    
        # Mostrar tabla de monitoreo en vivo para comprobar que el cálculo funciona
        df_consola = pd.DataFrame(datos_consola)
        consola_monitoreo.dataframe(df_consola, use_container_width=True)

    except Exception as e:
        consola_errores.error(f"❌ Error leyendo mercado en BingX: {e}")

    time.sleep(5)
    st.rerun()
