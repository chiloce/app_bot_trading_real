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
st.set_page_config(page_title="Crypto Execution Bot", layout="wide")
st.title("⚡ Bot de Ejecución Automatizada (Testnet)")
st.subheader("Entradas automáticas con Trailing Stop guiado")

# CONFIGURACIÓN DE LA BARRA LATERAL
st.sidebar.header("⚙️ Parámetros de Trading")
BOT_ENCENDIDO = st.sidebar.toggle("🤖 ACTIVAR BOT DE TRADING", value=False)
TIMEFRAME = st.sidebar.selectbox("Temporalidad de Análisis", ["15m", "4h"], index=0)
UMBRAL = st.sidebar.slider("Umbral de Disparo (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5)
MARGEN_USD = st.sidebar.number_input("Margen de Entrada (USD)", min_value=1.0, value=5.0, step=1.0)
LEVERAGE = st.sidebar.number_input("Apalancamiento (X)", min_value=1, max_value=25, value=10, step=1)
VOLUMEN_MINIMO = st.sidebar.number_input("Volumen mínimo 24h (USDT)", value=100000, step=50000)
TRAILING_PERC = st.sidebar.slider("Trailing Stop (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)

# =====================================================================
# CONEXIÓN OPTIMIZADA AL EXCHANGE
# =====================================================================
exchange = ccxt.binance({
    'apiKey': st.secrets["API_KEY_TESTNET"],
    'secret': st.secrets["SECRET_KEY_TESTNET"],
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',
        'adjustForTimeDifference': True
    }
})

exchange.set_sandbox_mode(True)
exchange.urls['api']['public'] = 'https://fapi.binance.com/fapi/v1'

# Contenedores visuales en la interfaz
metrica_estado = st.empty()
monitor_operacion = st.empty()

if BOT_ENCENDIDO:
    metrica_estado.success(f"🟢 BOT ENCENDIDO | Escaneando el mercado en [{TIMEFRAME}] esperando un {UMBRAL}%...")
else:
    metrica_estado.warning("🔴 BOT APAGADO | El modo de trading automático está desactivado.")
    monitor_operacion.info("Enciende el bot en la barra lateral para comenzar a buscar entradas.")

# Variable en caché para verificar si ya estamos dentro de una operación
if 'en_operacion' not in st.session_state:
    st.session_state.en_operacion = False
if 'detalles_operacion' not in st.session_state:
    st.session_state.detalles_operacion = {}

# =====================================================================
# FUNCIONES DE TRADING
# =====================================================================
def calcular_cantidad_contratos(symbol, precio_actual):
    try:
        valor_posicion_usd = MARGEN_USD * LEVERAGE
        cantidad_bruta = valor_posicion_usd / precio_actual
        exchange.load_markets()
        cantidad_ajustada = exchange.amount_to_precision(symbol, cantidad_bruta)
        return float(cantidad_ajustada)
    except Exception as e:
        print(f"Error calculando contratos: {e}")
        return 0

def abrir_posicion_con_trailing(symbol, direccion, precio_actual):
    try:
        cantidad = calcular_cantidad_contratos(symbol, precio_actual)
        if cantidad == 0: return False
        
        # 1. Forzar el Apalancamiento en el Exchange
        exchange.set_leverage(int(LEVERAGE), symbol)
        time.sleep(0.5)
        
        # 2. Lanzar Orden de Entrada a Mercado
        lado_entrada = 'buy' if direccion == 'LONG' else 'sell'
        orden_entrada = exchange.create_market_order(symbol, lado_entrada, cantidad)
        
        # 3. Lanzar Orden de Trailing Stop para la Salida
        lado_salida = 'sell' if direccion == 'LONG' else 'buy'
        params_trailing = {
            'callbackRate': TRAILING_PERC,
            'reduceOnly': True
        }
        orden_trailing = exchange.create_order(symbol, 'TRAILING_STOP_MARKET', lado_salida, cantidad, params=params_trailing)
        
        # Guardar estado local
        st.session_state.detalles_operacion = {
            "Par": symbol.split(':')[0],
            "Dirección": direccion,
            "Precio Entrada": precio_actual,
            "Cantidad": cantidad,
            "Valor Nominal": f"${MARGEN_USD * LEVERAGE} USD"
        }
        
        msg = f"🛒 ¡POSICIÓN ABIERTA AUTOMÁTICAMENTE!\n\nPar: {symbol.split(':')[0]}\nDirección: {direccion}\nPrecio: {precio_actual} USDT\nContratos: {cantidad}\n🎯 Trailing Stop colocado al {TRAILING_PERC}%"
        enviar_alerta(msg)
        return True
    except Exception as e:
        enviar_alerta(f"❌ Fallo al ejecutar trade en Binance: {e}")
        return False

# =====================================================================
# MOTOR DE ESCANEO CONTINUO (CORREGIDO)
# =====================================================================
if BOT_ENCENDIDO:
    if st.session_state.en_operacion:
        try:
            par_activo = st.session_state.detalles_operacion.get("Par")
            if ":" not in par_activo:
                par_activo = f"{par_activo}:USDT"
                
            posiciones = exchange.fetch_positions(symbols=[par_activo])
            if posiciones and float(posiciones[0]['info'].get('positionAmt', 0)) == 0:
                st.session_state.en_operacion = False
                enviar_alerta(f"🏁 La posición en {par_activo.split(':')[0]} ha sido cerrada por el Trailing Stop.")
        except Exception as e:
            print(f"Error verificando estado de la posición: {e}")

    if st.session_state.en_operacion:
        df_op = pd.DataFrame([st.session_state.detalles_operacion])
        monitor_operacion.dataframe(df_op, use_container_width=True)
    else:
        monitor_operacion.info("Vigilando el mercado... Ninguna operación abierta en este momento.")

    try:
        tickers = exchange.fetch_tickers()
        
        for symbol, info in tickers.items():
            if st.session_state.en_operacion:
                break
                
            # CORRECCIÓN: Filtra cualquier par con USDT de forma segura
            if not ('USDT' in symbol):
                continue
                
            variacion = info.get('percentage', 0)
            volumen = info.get('quoteVolume', 0)
            precio_actual = info.get('last', 0)
            
            if volumen < VOLUMEN_MINIMO or precio_actual == 0:
                continue

            direccion = None
            if variacion >= UMBRAL:
                direccion = "LONG"
            elif variacion <= -UMBRAL:
                direccion = "SHORT"

            if direccion and not st.session_state.en_operacion:
                # CORRECCIÓN: Convierte 'BTC/USDT' a 'BTC/USDT:USDT' para que la orden pase en futuros
                symbol_futuros = symbol if ":" in symbol else f"{symbol}:{symbol.split('/')[1]}"
                
                if abrir_posicion_con_trailing(symbol_futuros, direccion, precio_actual):
                    st.session_state.en_operacion = True
                    st.rerun()

    except Exception as e:
        print(f"Error en bucle de ejecución: {e}")

    time.sleep(8)
    st.rerun()
