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
st.title("⚡ Bot de Ejecución Automatizada (BingX)")
st.subheader("Entradas automáticas con Trailing Stop guiado")

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
    ins.load_markets() # Se descarga una sola vez y se guarda en memoria estable
    return ins

try:
    exchange = inicializar_exchange()
except Exception as e:
    st.error(f"❌ Error crítico de conexión a BingX: {e}")
    st.stop()
    
# Variables de estado preparadas desde el inicio
if 'en_operacion' not in st.session_state:
    st.session_state.en_operacion = False
if 'detalles_operacion' not in st.session_state:
    st.session_state.detalles_operacion = {}

# Contenedores visuales estables
metrica_estado = st.empty()
monitor_operacion = st.empty()
consola_monitoreo = st.empty()
consola_errores = st.empty()

if BOT_ENCENDIDO:
    metrica_estado.success(f"🟢 BOT ENCENDIDO | Analizando BingX [{TIMEFRAME}] esperando {UMBRAL}%...")
else:
    metrica_estado.warning("🔴 BOT APAGADO | El modo de trading automático está desactivado.")
    monitor_operacion.info("Enciende el bot en la barra lateral para comenzar a buscar entradas.")

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
        cantidad = calcular_cantidad_contratos(symbol, precio_actual)
        if cantidad == 0: return False
        
        # 1. Configurar Apalancamiento
        params_leverage = {'side': direccion}
        exchange.set_leverage(int(LEVERAGE), symbol, params=params_leverage)
        time.sleep(0.3)
        
        # 2. Orden de Entrada (Demo VST)
        lado_entrada = 'buy' if direccion == 'LONG' else 'sell'
        params_entrada = {
            'marginType': 'VST',
            'positionSide': direccion
        } 
        orden_entrada = exchange.create_market_order(symbol, lado_entrada, amount=cantidad, params=params_entrada)
        time.sleep(0.3)
        
       # 3. Orden de Trailing Stop (Formato Numérico Puro - Request con Debug)
        lado_salida = 'sell' if direccion == 'LONG' else 'buy'
        
        params_nativos = {
            'symbol': symbol.replace(':USDT', '').replace('/', ''),
            'type': 'TRAILING_STOP_MARKET',
            'side': lado_salida.upper(),
            'quantity': float(cantidad),
            'price': float(precio_actual),
            'activationPrice': float(precio_actual),
            'callbackRate': str(TRAILING_PERC / 100),
            'closePosition': True,
            'positionSide': direccion
        }
        
        try:
            orden_trailing = exchange.request(
                path='swap/v2/trade/order',
                api='private',
                method='POST',
                params=params_nativos
            )
        except Exception as e:
            # Si ccxt falla internamente, extraemos la respuesta cruda de BingX
            error_msg = str(e)
            if hasattr(e, 'feedback'):
                error_msg = f"{e.feedback}"
            elif hasattr(exchange, 'last_json_response') and exchange.last_json_response:
                error_msg = f"{exchange.last_json_response}"
            
            consola_errores.error(f"❌ Error detallado en Trailing Stop: {error_msg}")
            return False
        
        # Guardamos la información para pintar el cuadro azul estable
        st.session_state.detalles_operacion = {
            "Par": symbol.split('/')[0],
            "Dirección": direccion,
            "Precio Entrada": f"{precio_actual} USDT",
            "Cantidad": cantidad,
            "Valor Nominal": f"${MARGEN_USD * LEVERAGE} USD"
        }
        
        msg = f"🛒 ¡POSICIÓN ABIERTA EN BINGX!\n\nPar: {symbol.split('/')[0]}\nDirección: {direccion}\nPrecio: {precio_actual} USDT\n🎯 Trailing Stop colocado al {TRAILING_PERC}%"
        enviar_alerta(msg)
        return True
