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
st.subheader("Entradas automáticas con Trailing Stop guiado por Código (Máx 3 Trades)")

# CONFIGURACIÓN DE LA BARRA LATERAL
st.sidebar.header("⚙️ Parámetros de Trading")
BOT_ENCENDIDO = st.sidebar.toggle("🤖 ACTIVAR BOT DE TRADING", value=False)
TIMEFRAME = st.sidebar.selectbox("Temporalidad de Análisis", ["15m", "4h"], index=0)
UMBRAL = st.sidebar.slider("Umbral de Disparo (%)", min_value=0.01, max_value=5.0, value=0.10, step=0.01)
MARGEN_USD = st.sidebar.number_input("Margen de Entrada (USD)", min_value=1.0, value=5.0, step=1.0)
LEVERAGE = st.sidebar.number_input("Apalancamiento (X)", min_value=1, max_value=25, value=10, step=1)
VOLUMEN_MINIMO = st.sidebar.number_input("Volumen mínimo en vela (USDT)", value=10000, step=5000)
TRAILING_PERC = st.sidebar.slider("Trailing Stop (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)

# =====================================================================
# CONEXIÓN OPTIMIZADA CON CACHÉ (EVITA BUCLES INFINITOS)
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

# Contenedores visuales dinámicos superiores
metrica_estado = st.empty()
col_bal1, col_bal2, col_bal3 = st.columns(3)
p1 = col_bal1.empty()
p2 = col_bal2.empty()
p3 = col_bal3.empty()

st.markdown("---")
st.subheader("📊 Panel de Operaciones Activas")
monitor_operacion = st.empty()

st.markdown("---")
st.subheader("🔍 Monitoreo del Mercado en Vivo")
consola_monitoreo = st.empty()

st.markdown("---")
st.subheader("📜 Historial de Operaciones Cerradas")
tabla_historial = st.empty()
consola_errores = st.empty()

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
        consola_errores.error(f"⚠️ Error calculando tamaño de posición: {e}")
        return 0

def abrir_posicion_con_trailing(symbol, direccion, precio_actual):
    try:
        token = symbol.split('/')[0]
        cantidad = calcular_cantidad_contratos(symbol, precio_actual)
        if cantidad == 0: return False
        
        params_leverage = {'side': direccion}
        exchange.set_leverage(int(LEVERAGE), symbol, params=params_leverage)
        time.sleep(0.3)
        
        lado_entrada = 'buy' if direccion == 'LONG' else 'sell'
        params_entrada = {
            'marginType': 'VST',
            'positionSide': direccion
        } 
        orden_entrada = exchange.create_market_order(symbol, lado_entrada, amount=cantidad, params=params_entrada)
        
        if direccion == "LONG":
            stop_inicial = precio_actual * (1 - (TRAILING_PERC / 100))
        else:
            stop_inicial = precio_actual * (1 + (TRAILING_PERC / 100))
            
        st.session_state.operaciones_activas[token] = {
            "Par": token,
            "Symbol_Completo": symbol,
            "Dirección": direccion,
            "Precio Entrada": precio_actual,
            "Cantidad": cantidad,
            "Valor Nominal": f"${MARGEN_USD * LEVERAGE} USD",
            "Trailing Stop Activo": float(stop_inicial),
            "Precio Máximo Alcanzado": float(precio_actual)
        }
        
        msg = f"🛒 ¡POSICIÓN ABIERTA!\n\nPar: {token}\nDirección: {direccion}\nPrecio: {precio_actual} USDT\n🎯 Trailing Stop: {stop_inicial:.4f} USDT"
        enviar_alerta(msg)
        return True
    except Exception as e:
        print(f"Error abriendo posición: {e}")
        return False

# =====================================================================
# BUCLE EN VIVO SIN REFRESCAR PÁGINA (SOLUCIÓN AL PARPADEO)
# =====================================================================
if not BOT_ENCENDIDO:
    metrica_estado.warning("🔴 BOT APAGADO | El modo de trading automático está desactivado.")
    monitor_operacion.info("Enciende el bot en la barra lateral para comenzar a buscar entradas.")
    if st.session_state.historial_trades:
        tabla_historial.dataframe(pd.DataFrame(st.session_state.historial_trades), use_container_width=True)
    else:
        tabla_historial.info("Aún no hay operaciones cerradas en esta sesión.")
else:
    PARES_A_REVISAR = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT", "XRP/USDT:USDT"]
    
    # Este while True mantiene el bot corriendo por dentro de forma fluida
    while BOT_ENCENDIDO:
        try:
            # 1. ACTUALIZAR FONDOS (UI estática, valores dinámicos)
            balance = exchange.fetch_balance(params={'currency': 'VST'})
            vst_libre = float(balance['info']['data']['balance']['availableMargin'])
            vst_total = float(balance['info']['data']['balance']['equity'])
            
            p1.metric(label="💰 Capital Total (VST)", value=f"{vst_total:,.2f} VST")
            p2.metric(label="🔓 Margen Disponible", value=f"{vst_libre:,.2f} VST")
            p3.metric(label="🔄 Ranuras Usadas", value=f"{len(st.session_state.operaciones_activas)} de 3 abiertas")
            
            metrica_estado.success(f"🟢 BOT ENCENDIDO | Escaneando BingX [{TIMEFRAME}]. Buscando señales... (Ranuras: {len(st.session_state.operaciones_activas)}/3)")

            # 2. SEGUIMIENTO DE TRAILING STOPS ACTIVOS
            tokens_abiertos = list(st.session_state.operaciones_activas.keys())
            for token in tokens_abiertos:
                try:
                    op = st.session_state.operaciones_activas.get(token)
                    if not op: continue
                    
                    symbol_activo = op.get("Symbol_Completo")
                    ticker = exchange.fetch_ticker(symbol_activo)
                    precio_vivo = float(ticker['last'])
                    
                    direccion = op.get("Dirección")
                    stop_actual = op.get("Trailing Stop Activo")
                    max_precio = op.get("Precio Máximo Alcanzado")
                    precio_entrada = op.get("Precio Entrada")
                    cantidad = op.get("Cantidad")
                    
                    if direccion == "LONG":
                        if precio_vivo > max_precio:
                            st.session_state.operaciones_activas[token]["Precio Máximo Alcanzado"] = precio_vivo
                            nuevo_stop = precio_vivo * (1 - (TRAILING_PERC / 100))
                            if nuevo_stop > stop_actual:
                                st.session_state.operaciones_activas[token]["Trailing Stop Activo"] = float(nuevo_stop)
                        
                        if precio_vivo <= stop_actual:
                            exchange.create_market_order(symbol_activo, 'sell', amount=cantidad, params={'marginType': 'VST', 'positionSide': 'LONG'})
                            del st.session_state.operaciones_activas[token]
                            pnl = (precio_vivo - precio_entrada) * cantidad
                            st.session_state.historial_trades.append({
                                "Fecha/Hora": time.strftime("%Y-%m-%d %H:%M:%S"), "Par": token, "Dirección": direccion,
                                "Precio Entrada": precio_entrada, "Precio Cierre": precio_vivo, "PnL Estimado": f"{pnl:+.4f} VST"
                            })
                            enviar_alerta(f"🏁 Trailing Stop en {token}. Resultado: {pnl:+.2f} VST")
                            
                    elif direccion == "SHORT":
                        if precio_vivo < max_precio:
                            st.session_state.operaciones_activas[token]["Precio Máximo Alcanzado"] = precio_vivo
                            nuevo_stop = precio_vivo * (1 + (TRAILING_PERC / 100))
                            if nuevo_stop < stop_actual:
                                st.session_state.operaciones_activas[token]["Trailing Stop Activo"] = float(nuevo_stop)
                        
                        if precio_vivo >= stop_actual:
                            exchange.create_market_order(symbol_activo, 'buy', amount=cantidad, params={'marginType': 'VST', 'positionSide': 'SHORT'})
                            del st.session_state.operaciones_activas[token]
                            pnl = (precio_entrada - precio_vivo) * cantidad
                            st.session_state.historial_trades.append({
                                "Fecha/Hora": time.strftime("%Y-%m-%d %H:%M:%S"), "Par": token, "Dirección": direccion,
                                "Precio Entrada": precio_entrada, "Precio Cierre": precio_vivo, "PnL Estimado": f"{pnl:+.4f} VST"
                            })
                            enviar_alerta(f"🏁 Trailing Stop en {token}. Resultado: {pnl:+.2f} VST")
                except Exception as e:
                    print(f"Error procesando trailing vivo: {e}")

            # DIBUJAR OPERACIONES ACTIVAS SIN PARPADEO
            if st.session_state.operaciones_activas:
                df_op = pd.DataFrame(st.session_state.operaciones_activas.values())
                columnas_orden = ["Par", "Dirección", "Precio Entrada", "Cantidad", "Valor Nominal", "Trailing Stop Activo", "Precio Máximo Alcanzado"]
                monitor_operacion.dataframe(df_op[columnas_orden], use_container_width=True)
            else:
                monitor_operacion.info("Vigilando los pares en BingX... Sin operaciones abiertas en este momento.")

            # 3. ESCANEO CONTINUO DEL MERCADO
            datos_consola = []
            for symbol in PARES_A_REVISAR:
                try:
                    token_curr = symbol.split('/')[0]
                    velas = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=2)
                    if len(velas) < 2: continue
                    
                    vela_actual = velas[-1]
                    precio_apertura = vela_actual[1]
                    precio_actual = vela_actual[4]
                    volumen_vela = vela_actual[5] * precio_actual
                    variacion = ((precio_actual - precio_apertura) / precio_apertura) * 100
                    
                    datos_consola.append({
                        "Moneda": token_curr, "Precio Actual": f"{precio_actual} USDT",
                        "Variación Vela": f"{variacion:.3f}%", "Volumen": f"${volumen_vela:,.0f} USD"
                    })
                    
                    if token_curr in st.session_state.operaciones_activas or len(st.session_state.operaciones_activas) >= 3:
                        continue
                        
                    if volumen_vela < VOLUMEN_MINIMO:
                        continue
                    
                    direccion_disparo = None
                    if variacion >= UMBRAL: direccion_disparo = "LONG"
                    elif variacion <= -UMBRAL: direccion_disparo = "SHORT"

                    if direccion_disparo:
                        abrir_posicion_con_trailing(symbol, direccion_disparo, precio_actual)
                except Exception as e:
                    print(f"Error escaneando {symbol}: {e}")
            
            # REEMPLAZAR TABLA EN VIVO SIN BORRARLA ANTES
            if datos_consola:
                consola_monitoreo.dataframe(pd.DataFrame(datos_consola), use_container_width=True)

            # REEMPLAZAR HISTORIAL SIN PARPADEO
            if st.session_state.historial_trades:
                tabla_historial.dataframe(pd.DataFrame(st.session_state.historial_trades), use_container_width=True)
            else:
                tabla_historial.info("Aún no hay operaciones cerradas en esta sesión.")

        except Exception as e:
            print(f"Error general en el bucle: {e}")
            
        time.sleep(5) # Espera de 5 segundos antes de reescribir los contenedores
