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
VOLUMEN_MINIMO = st.sidebar.number_input("Volumen mínimo 24h (USDT)", value=500000, step=100000) # <-- NUEVA LÍNEA (Inicia en 500k)
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
        'adjustForTimeDifference': True # Corrige el desfase de reloj del servidor
    }
})

# Forzar operaciones y órdenes exclusivamente en el entorno de pruebas
exchange.set_sandbox_mode(True)

# TRUCO TÁCTICO PARA LA NUBE:
# Forzamos a que la lectura pública de precios sea en la API comercial estable,
# pero las funciones privadas (crear órdenes, apalancamiento) apunten a la Testnet.
exchange.urls['api']['public'] = 'https://fapi.binance.com/fapi/v1'

# Contenedores visuales en la interfaz
metrica_estado = st.empty()
monitor_operacion = st.empty()

# =====================================================================
# MOTOR DE ESCANEO CONTINUO (CORREGIDO Y ADAPTADO)
# =====================================================================
if BOT_ENCENDIDO:
    # Si localmente creemos que estamos en operación, verificar en Binance si sigue abierta
    if st.session_state.en_operacion:
        try:
            par_activo = st.session_state.detalles_operacion.get("Par")
            # Adaptar formato para la consulta de posiciones en futuros perpetuos
            if ":" not in par_activo:
                par_activo = f"{par_activo}:USDT"
                
            posiciones = exchange.fetch_positions(symbols=[par_activo])
            if posiciones and float(posiciones[0]['info'].get('positionAmt', 0)) == 0:
                st.session_state.en_operacion = False
                enviar_alerta(f"🏁 La posición en {par_activo.split(':')[0]} ha sido cerrada por el Trailing Stop.")
        except Exception as e:
            print(f"Error verificando estado de la posición: {e}")

    # Mostrar visualmente si hay una operación activa
    if st.session_state.en_operacion:
        df_op = pd.DataFrame([st.session_state.detalles_operacion])
        monitor_operacion.dataframe(df_op, use_container_width=True)
    else:
        monitor_operacion.info("Vigilando el mercado... Ninguna operación abierta en este momento.")

    try:
        # Escaneo masivo de los tickers comerciales
        tickers = exchange.fetch_tickers()
        
        for symbol, info in tickers.items():
            # Evitar buscar si ya estamos dentro de una operación
            if st.session_state.en_operacion:
                break
                
            # Filtrar solo pares que operen contra USDT (ej: BTC/USDT o BTC/USDT:USDT)
            if not ('USDT' in symbol):
                continue
                
            variacion = info.get('percentage', 0)
            volumen = info.get('quoteVolume', 0)
            precio_actual = info.get('last', 0)
            
            # Filtro de volumen dinámico de la barra lateral
            if volumen < VOLUMEN_MINIMO or precio_actual == 0:
                continue

            # Evaluar quiebre del umbral configurado
            direccion = None
            if variacion >= UMBRAL:
                direccion = "LONG"
            elif variacion <= -UMBRAL:
                direccion = "SHORT"

            # DISPARAR ENTRADA REAL (Formateando el par correctamente para Futuros)
            if direccion and not st.session_state.en_operacion:
                # Asegurar formato estricto de CCXT Futuros Perpetuos para la orden (ej: BTC/USDT:USDT)
                symbol_futuros = symbol if ":" in symbol else f"{symbol}:{symbol.split('/')[1]}"
                
                if abrir_posicion_con_trailing(symbol_futuros, direccion, precio_actual):
                    st.session_state.en_operacion = True
                    st.rerun()

    except Exception as e:
        print(f"Error en bucle de ejecución: {e}")

    # Ciclo de consulta cada 8 segundos
    time.sleep(8)
    st.rerun()
