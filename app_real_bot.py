import streamlit as st
import ccxt
import pandas as pd
import time
import requests

# =====================================================================
# CONFIGURACIÓN DE NOTIFICACIONES (TELEGRAM)
# =====================================================================
TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]

def enviar_alerta(mensaje):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje})
        except Exception as e: print(f"Error Telegram: {e}")

# =====================================================================
# INTERFAZ WEB (STREAMLIT)
# =====================================================================
st.set_page_config(page_title="Crypto Execution Bot (BingX)", layout="wide")
st.title("⚡ Bot de Ejecución Automatizada Multi-Trade (BingX)")
st.subheader("Escaneo Masivo de Alta Velocidad con Stops Blindados (Máx 10 Trades)")

# CONFIGURACIÓN DE LA BARRA LATERAL
st.sidebar.header("⚙️ Parámetros de Trading")
BOT_ENCENDIDO = st.sidebar.toggle("🤖 ACTIVAR BOT DE TRADING", value=False)
TIMEFRAME = st.sidebar.selectbox("Temporalidad de Análisis", ["15m", "4h"], index=0)
UMBRAL = st.sidebar.slider("Umbral de Disparo (%)", min_value=0.01, max_value=15.0, value=5.0, step=0.01)
MARGEN_USD = st.sidebar.number_input("Margen de Entrada (USD)", min_value=1.0, value=5.0, step=1.0)
LEVERAGE = st.sidebar.number_input("Apalancamiento (X)", min_value=1, max_value=25, value=10, step=1)
VOLUMEN_MINIMO = st.sidebar.number_input("Volumen mínimo en vela (USDT)", value=10000, step=5000)
TRAILING_PERC = st.sidebar.slider("Trailing Stop (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)

# CONTENEDORES VISUALES FIJOS
metrica_estado = st.empty()
panel_balance = st.columns(3)
p1 = panel_balance[0].empty()
p2 = panel_balance[1].empty()
p3 = panel_balance[2].empty()

st.markdown("---")
st.subheader("📊 Panel de Operaciones Activas (Sincronizado con Exchange)")
monitor_operacion = st.empty()

st.markdown("---")
st.subheader("🔍 Monitoreo del Mercado en Vivo (Filtro Inteligente de Impulso)")
consola_monitoreo = st.empty()

st.markdown("---")
st.subheader("📜 Historial de Operaciones Cerradas")
tabla_historial = st.empty()
consola_errores = st.empty()

# =====================================================================
# CONEXIÓN OPTIMIZADA CON CACHÉ
# =====================================================================
@st.cache_resource
def inicializar_exchange():
    ins = ccxt.bingx({
        'apiKey': st.secrets["API_KEY_TESTNET"],
        'secret': st.secrets["SECRET_KEY_TESTNET"],
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    ins.set_sandbox_mode(True)
    ins.load_markets()
    return ins

try:
    exchange = inicializar_exchange()
except Exception as e:
    st.error(f"❌ Error crítico de conexión a BingX: {e}")
    st.stop()
    
if 'operaciones_activas' not in st.session_state:
    st.session_state.operaciones_activas = {}
if 'historial_trades' not in st.session_state:
    st.session_state.historial_trades = []

# =====================================================================
# FUNCIONES DE TRADING (BINGX)
# =====================================================================
def calcular_cantidad_contratos(symbol, precio_actual):
    try:
        valor_posicion_usd = MARGEN_USD * LEVERAGE
        cantidad_bruta = valor_posicion_usd / precio_actual
        cantidad_ajustada = exchange.amount_to_precision(symbol, cantidad_bruta)
        return float(cantidad_ajustada)
    except Exception as e:
        return 0

def abrir_posicion_con_trailing(symbol, direccion, precio_actual):
    try:
        token = symbol.split('/')[0]
        cantidad = calcular_cantidad_contratos(symbol, precio_actual)
        if cantidad == 0: return False
        
        params_leverage = {'side': direccion}
        exchange.set_leverage(int(LEVERAGE), symbol, params=params_leverage)
        time.sleep(0.2)
        
        lado_entrada = 'buy' if direccion == 'LONG' else 'sell'
        params_entrada = { 'marginType': 'VST', 'positionSide': direccion } 
        orden_entrada = exchange.create_market_order(symbol, lado_entrada, amount=cantidad, params=params_entrada)
        
        if direccion == "LONG":
            stop_sucio = precio_actual * (1 - (TRAILING_PERC / 100))
        else:
            stop_sucio = precio_actual * (1 + (TRAILING_PERC / 100))
            
        # CORREGIDO: price_to_string para evitar errores de versión en CCXT
        stop_inicial = float(exchange.price_to_string(symbol, stop_sucio))
            
        st.session_state.operaciones_activas[token] = {
            "Par": token, "Symbol_Completo": symbol, "Dirección": direccion, "Precio Entrada": precio_actual,
            "Cantidad": cantidad, "Valor Nominal": f"${MARGEN_USD * LEVERAGE} USD",
            "Trailing Stop Activo": stop_inicial, "Precio Extremo": float(precio_actual)
        }
        
        enviar_alerta(f"🛒 ¡ENTRADA POR IMPULSO DISPARADA!\n\nPar: {token}\nDirección: {direccion}\nPrecio: {precio_actual} USDT")
        return True
    except Exception as e:
        return False

# =====================================================================
# BUCLE PRINCIPAL DE EJECUCIÓN (LÓGICA LINEAL SEGURA)
# =====================================================================
if BOT_ENCENDIDO:
    metrica_estado.success(f"🟢 BOT ENCENDIDO | Escaneando el mercado de forma segura y optimizada...")
    
    # MÓDULO DE ACTUALIZACIÓN DE BALANCE (VST)
    try:
        balance = exchange.fetch_balance(params={'currency': 'VST'})
        vst_libre = float(balance.get('free', {}).get('VST', 0.0))
        vst_total = float(balance.get('total', {}).get('VST', 0.0))
        
        if vst_total == 0.0 and 'info' in balance and 'data' in balance['info']:
            data_bal = balance['info']['data']
            if isinstance(data_bal, dict) and 'balance' in data_bal:
                vst_libre = float(data_bal['balance'].get('availableMargin', 0.0))
                vst_total = float(data_bal['balance'].get('equity', 0.0))
            elif isinstance(data_bal, list) and len(data_bal) > 0:
                vst_libre = float(data_bal[0].get('availableMargin', 0.0))
                vst_total = float(data_bal[0].get('equity', 0.0))

        p1.metric(label="💰 Capital Total (VST)", value=f"{vst_total:,.2f} VST")
        p2.metric(label="🔓 Margen Disponible", value=f"{vst_libre:,.2f} VST")
        p3.metric(label="🔄 Ranuras Usadas", value=f"{len(st.session_state.operaciones_activas)} de 10 abiertas")
    except Exception as e:
        consola_errores.error(f"⚠️ Aviso balance VST: {e}")

    try:
        mercados = exchange.load_markets()
        PARES_A_REVISAR = [symbol for symbol in mercados.keys() if symbol.endswith('/USDT:USDT')]
    except Exception as e:
        PARES_A_REVISAR = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]

    dict_sincronizado = {}

    # SINCRONIZACIÓN DIRECTA DESDE EXCHANGE BLINDADA
    try:
        posiciones_exchange = exchange.fetch_positions()
        if isinstance(posiciones_exchange, list):
            for pos in posiciones_exchange:
                if not isinstance(pos, dict): continue
                amount_pos = pos.get('contracts')
                cantidad_ex = float(amount_pos if amount_pos is not None else 0)
                if cantidad_ex > 0:
                    symbol_ex = pos.get('symbol')
                    if not symbol_ex: continue
                    token_ex = symbol_ex.split('/')[0]
                    
                    if symbol_ex in PARES_A_REVISAR:
                        direccion_ex = pos.get('side', '').upper()
                        precio_entrada_ex = float(pos.get('entryPrice', 0))
                        precio_actual_ex = float(pos.get('markPrice', precio_entrada_ex))
                        
                        if token_ex in st.session_state.operaciones_activas:
                            dict_sincronizado[token_ex] = st.session_state.operaciones_activas[token_ex]
                        else:
                            if direccion_ex == "LONG":
                                stop_sucio = precio_entrada_ex * (1 - (TRAILING_PERC / 100))
                            else:
                                stop_sucio = precio_entrada_ex * (1 + (TRAILING_PERC / 100))
                            
                            # CORREGIDO: price_to_string
                            stop_inicial = float(exchange.price_to_string(symbol_ex, stop_sucio))
                                
                            dict_sincronizado[token_ex] = {
                                "Par": token_ex, "Symbol_Completo": symbol_ex, "Dirección": direccion_ex, "Precio Entrada": precio_entrada_ex,
                                "Cantidad": cantidad_ex, "Valor Nominal": f"${cantidad_ex * precio_entrada_ex:.1f} USD",
                                "Trailing Stop Activo": stop_inicial, "Precio Extremo": float(precio_actual_ex)
                            }
            st.session_state.operaciones_activas = dict_sincronizado
    except Exception as e:
        print(f"Error sincronización pos: {e}")

    # GESTIÓN Y MONITOR DE TRAILING STOP
    tokens_abiertos = list(st.session_state.operaciones_activas.keys())
    necesita_rerun = False
    
    for token in tokens_abiertos:
        try:
            op = st.session_state.operaciones_activas.get(token)
            if not op or not isinstance(op, dict): continue
            
            symbol_activo = op.get("Symbol_Completo")
            ticker = exchange.fetch_ticker(symbol_activo)
            precio_vivo = float(ticker['last'])
            
            direccion = op.get("Dirección")
            stop_actual = op.get("Trailing Stop Activo")
            extremo_precio = op.get("Precio Extremo")
            precio_entrada = op.get("Precio Entrada")
            cant = op.get("Cantidad")
            
            if direccion == "LONG":
                if precio_vivo > extremo_precio:
                    st.session_state.operaciones_activas[token]["Precio Extremo"] = precio_vivo
                    nuevo_stop_sucio = precio_vivo * (1 - (TRAILING_PERC / 100))
                    # CORREGIDO: price_to_string
                    nuevo_stop = float(exchange.price_to_string(symbol_activo, nuevo_stop_sucio))
                    if nuevo_stop > stop_actual:
                        st.session_state.operaciones_activas[token]["Trailing Stop Activo"] = nuevo_stop
                
                if precio_vivo <= stop_actual:
                    exchange.create_market_order(symbol_activo, 'sell', amount=cant, params={'marginType': 'VST', 'positionSide': 'LONG'})
                    del st.session_state.operaciones_activas[token]
                    pnl = (precio_vivo - precio_entrada) * cant
                    st.session_state.historial_trades.append({
                        "Fecha/Hora": time.strftime("%Y-%m-%d %H:%M:%S"), "Par": token, "Dirección": direccion,
                        "Precio Entrada": precio_entrada, "Precio Cierre": precio_vivo, "PnL Estimado": f"{pnl:+.4f} VST"
                    })
                    enviar_alerta(f"🏁 Trailing Stop ejecutado en LONG para {token}. Resultado: {pnl:+.2f} VST")
                    necesita_rerun = True
                    
            elif direccion == "SHORT":
                if precio_vivo < extremo_precio:
                    st.session_state.operaciones_activas[token]["Precio Extremo"] = precio_vivo
                    nuevo_stop_sucio = precio_vivo * (1 + (TRAILING_PERC / 100))
                    # CORREGIDO: price_to_string
                    nuevo_stop = float(exchange.price_to_string(symbol_activo, nuevo_stop_sucio))
                    if nuevo_stop < stop_actual:
                        st.session_state.operaciones_activas[token]["Trailing Stop Activo"] = nuevo_stop
                
                if precio_vivo >= stop_actual:
                    exchange.create_market_order(symbol_activo, 'buy', amount=cant, params={'marginType': 'VST', 'positionSide': 'SHORT'})
                    del st.session_state.operaciones_activas[token]
                    pnl = (precio_entrada - precio_vivo) * cant
                    st.session_state.historial_trades.append({
                        "Fecha/Hora": time.strftime("%Y-%m-%d %H:%M:%S"), "Par": token, "Dirección": direccion,
                        "Precio Entrada": precio_entrada, "Precio Cierre": precio_vivo, "PnL Estimado": f"{pnl:+.4f} VST"
                    })
                    enviar_alerta(f"🏁 Trailing Stop ejecutado en SHORT para {token}. Resultado: {pnl:+.2f} VST")
                    necesita_rerun = True
        except Exception as e:
            print(f"Error trailing: {e}")

    if necesita_rerun:
        st.rerun()

    # PANEL INTERACTIVO DE OPERACIONES ACTIVAS
    columnas_orden = ["Par", "Dirección", "Precio Entrada", "Cantidad", "Valor Nominal", "Trailing Stop Activo", "Precio Extremo", "Cerrar Trade"]
    
    if st.session_state.operaciones_activas:
        df_op = pd.DataFrame(st.session_state.operaciones_activas.values())
        df_op["Cerrar Trade"] = False
        
        evento_cierre = monitor_operacion.data_editor(
            df_op[columnas_orden],
            column_config={"Cerrar Trade": st.column_config.CheckboxColumn("Cerrar de Emergencia", default=False)},
            disabled=["Par", "Dirección", "Precio Entrada", "Cantidad", "Valor Nominal", "Trailing Stop Activo", "Precio Extremo"],
            width='stretch', key="editor_posiciones"
        )
        
        for i, row in evento_cierre.iterrows():
            if row["Cerrar Trade"] == True:
                token_a_cerrar = row["Par"]
                op_detalles = st.session_state.operaciones_activas[token_a_cerrar]
                lado_cierre = 'sell' if op_detalles["Dirección"] == 'LONG' else 'buy'
                try:
                    exchange.create_market_order(op_detalles["Symbol_Completo"], lado_cierre, amount=op_detalles["Cantidad"], params={'marginType': 'VST', 'positionSide': op_detalles["Dirección"]})
                    del st.session_state.operaciones_activas[token_a_cerrar]
                    st.session_state.historial_trades.append({
                        "Fecha/Hora": time.strftime("%Y-%m-%d %H:%M:%S"), "Par": token_a_cerrar, "Dirección": op_detalles["Dirección"],
                        "Precio Entrada": op_detalles["Precio Entrada"], "Precio Cierre": "Manual Web", "PnL Estimado": "Manual"
                    })
                    st.rerun()
                except Exception as e: pass
    else:
        df_vacio = pd.DataFrame(columns=columnas_orden)
        monitor_operacion.data_editor(df_vacio, width='stretch', disabled=columnas_orden, key="editor_posiciones_vacio")
        monitor_operacion.info("Sincronizado. Sin posiciones abiertas en BingX en este momento.")

    # 🔍 PASO 3: ESCANEO HÍBRIDO DE MERCADO
    datos_consola = []
    
    try:
        tickers = exchange.fetch_tickers(PARES_A_REVISAR)
        
        pares_candidatos = []
        for symbol in PARES_A_REVISAR:
            if symbol in tickers:
                precio_actual = float(tickers[symbol]['last'])
                var_24h = tickers[symbol]['percentage']
                variacion_24h = float(var_24h if var_24h is not None else 0.0)
                pares_candidatos.append((symbol, abs(variacion_24h)))
        
        pares_candidatos = sorted(pares_candidatos, key=lambda x: x[1], reverse=True)[:15]
        top_15_symbols = [p[0] for p in pares_candidatos]

        for symbol in top_15_symbols:
            try:
                token_curr = symbol.split('/')[0]
                precio_actual = float(tickers[symbol]['last'])
                var_24h = tickers[symbol]['percentage']
                variacion_24h = float(var_24h if var_24h is not None else 0.0)
                v_base = tickers[symbol]['baseVolume']
                volumen_24h = float(v_base * precio_actual if v_base is not None else 0.0)
                
                velas = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=2)
                if len(velas) < 2: continue
                
                vela_actual = velas[-1]
                precio_apertura_15m = float(vela_actual[1])
                precio_actual_15m = float(vela_actual[4])
                variacion_vela_real = ((precio_actual_15m - precio_apertura_15m) / precio_apertura_15m) * 100
                
                datos_consola.append({
                    "Moneda": token_curr, 
                    "Precio Actual": f"{precio_actual_15m} USDT",
                    "Movimiento 24h": f"{variacion_24h:+.2f}%",
                    "Variación Vela (15m)": variacion_vela_real, 
                    "Volumen 24h": f"${volumen_24h:,.0f} USD"
                })
                
                if token_curr in st.session_state.operaciones_activas or len(st.session_state.operaciones_activas) >= 10:
                    continue
                    
                if volumen_24h < VOLUMEN_MINIMO:
                    continue
                
                direccion_disparo = None
                if variacion_vela_real >= UMBRAL: 
                    direccion_disparo = "LONG"
                elif variacion_vela_real <= -UMBRAL: 
                    direccion_disparo = "SHORT"

                if direccion_disparo:
                    if abrir_posicion_con_trailing(symbol, direccion_disparo, precio_actual_15m):
                        st.rerun()
            except Exception as e: 
                continue
                
        if datos_consola:
            df_consola = pd.DataFrame(datos_consola)
            df_consola["Var_Abs"] = df_consola["Variación Vela (15m)"].abs()
            df_consola = df_consola.sort_values(by="Var_Abs", ascending=False).drop(columns=["Var_Abs"])
            
            df_consola["Variación Vela (15m)"] = df_consola["Variación Vela (15m)"].map(lambda x: f"{x:+.3f}%")
            consola_monitoreo.dataframe(df_consola, width='stretch')

    except Exception as e:
        print(f"Error crítico en escaneo masivo: {e}")

# PINTAR EL HISTORIAL DE TRADES
if st.session_state.historial_trades:
    df_historial = pd.DataFrame(st.session_state.historial_trades)
    tabla_historial.dataframe(df_historial, width='stretch')
else:
    tabla_historial.info("Aún no hay operaciones cerradas en esta sesión.")

# REFRESCAR CADA 5 SEGUNDOS
if BOT_ENCENDIDO:
    time.sleep(5)
    st.rerun()
else:
    metrica_estado.warning("🔴 BOT APAGADO | El modo de trading automático está desactivado.")
    monitor_operacion.info("Enciende el bot en la barra lateral para comenzar a buscar entradas.")
