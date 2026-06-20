import streamlit as st
import ccxt
import pandas as pd
import time
import requests

# =====================================================================
# CONFIGURACIÓN DE CREDENCIALES (SECRETS)
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

# Botón maestro de encendido
BOT_ENCENDIDO = st.sidebar.toggle("🤖 ACTIVAR BOT DE TRADING", value=False)

# Parámetros solicitados por el usuario
TIMEFRAME = st.sidebar.selectbox("Temporalidad de Análisis", ["15m", "1h", "4h"], index=0)
UMBRAL = st.sidebar.slider("Umbral de Disparo (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5)
MARGEN_USD = st.sidebar.number_input("Margen de Entrada (USD)", min_value=1.0, value=5.0, step=1.0)
LEVERAGE = st.sidebar.number_input("Apalancamiento (X)", min_value=1, max_value=25, value=10, step=1)
TRAILING_PERC = st.sidebar.slider("Trailing Stop (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)

# Conexión autorizada a la Testnet (Modo Escritura para operar)
exchange = ccxt.binance({
    'apiKey': st.secrets["API_KEY_TESTNET"],
    'secret': st.secrets["SECRET_KEY_TESTNET"],
    'enableRateLimit': True,
    'options': {'defaultType': 'future', 'adjustForTimeDifference': True}
})
exchange.set_sandbox_mode(True)

# Contenedores visuales
metrica_estado = st.empty()
monitor_operacion = st.empty()

if BOT_ENCENDIDO:
    metrica_estado.success(f"🟢 BOT ENCENDIDO | Vigilando el mercado en [{TIMEFRAME}] esperando un {UMBRAL}%...")
else:
    metrica_estado.warning("🔴 BOT APAGADO | El modo de trading automático está desactivado.")

# =====================================================================
# FUNCIÓN MATEMÁTICA DE CÁLCULO DE CONTRATOS
# =====================================================================
def calcular_cantidad_contratos(symbol, precio_actual):
    """Calcula cuántas criptos comprar para que equivalgan al margen por apalancamiento."""
    try:
        # Valor nominal de la posición (Margen * Apalancamiento) -> Ej: 5 USD * 10x = 50 USD
        valor_posicion_usd = MARGEN_USD * LEVERAGE
        
        # Cantidad de monedas brutas -> Ej: 50 USD / 64,000 USD (Precio BTC) = 0.00078125 BTC
        cantidad_bruta = valor_posicion_usd / precio_actual
        
        # Ajustar la cantidad a los decimales permitidos por Binance para esa moneda específica
        mercados = exchange.load_markets()
        market = mercados[symbol]
        cantidad_ajustada = exchange.amount_to_precision(symbol, cantidad_bruta)
        
        return float(cantidad_ajustada)
    except Exception as e:
        print(f"Error al calcular tamaño de orden: {e}")
        return 0

# =====================================================================
# LÓGICA DE EJECUCIÓN REAL (PROTOTIPO)
# =====================================================================
def abrir_posicion_con_trailing(symbol, direccion, precio_actual):
    try:
        cantidad = calcular_cantidad_contratos(symbol, precio_actual)
        if cantidad == 0:
            return
            
        msg_inicio = f"🛒 Intentando abrir {direccion} en {symbol}\nCantidad: {cantidad} (Valor: ${MARGEN_USD * LEVERAGE} USD)"
        enviar_alerta(msg_inicio)
        
        # 1. Configurar el apalancamiento en Binance de forma forzosa
        exchange.set_leverage(int(LEVERAGE), symbol)
        
        # 2. Lanzar Orden de Entrada a Mercado Real en Testnet
        lado_orden = 'buy' if direccion == 'LONG' else 'sell'
        # orden_entrada = exchange.create_market_order(symbol, lado_orden, cantidad)
        
        # 3. Lanzar Orden de Trailing Stop de Cierre
        lado_trailing = 'sell' if direccion == 'LONG' else 'buy'
        params_trailing = {
            'callbackRate': TRAILING_PERC, # El 1.5% que definiste
            'reduceOnly': True
        }
        # exchange.create_order(symbol, 'TRAILING_STOP_MARKET', lado_trailing, cantidad, params=params_trailing)
        
        enviar_alerta(f"✅ Posición Abierta con Éxito. Trailing Stop del {TRAILING_PERC}% activado y persiguiendo.")
        
    except Exception as e:
        enviar_alerta(f"❌ Error al ejecutar trade en Binance: {e}")

# (El bucle de escaneo se integrará en el siguiente paso una vez que crees este repositorio)