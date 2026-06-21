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
# CONEXIÓN NATIVA A BINGX CON SANDBOX FORZADO (LIMPIEZA DE CACHÉ)
# =====================================================================
exchange = ccxt.bingx({
    'apiKey': st.secrets["API_KEY_TESTNET"],
    'secret': st.secrets["SECRET_KEY_TESTNET"],
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap' # Conecta directamente a Futuros Perpetuos
    }
})

# Forzar el entorno Sandbox de simulación VST
exchange.set_sandbox_mode(True)

# Cargar mercados de forma segura en cada ciclo limpio
try:
    exchange.load_markets()
except Exception as e:
    print(f"Error cargando mercados: {e}")

# Contenedores visuales en la interfaz
metrica_estado = st.empty()
monitor_operacion = st.empty()
consola_monitoreo = st.empty()
consola_errores = st.empty()

if BOT_ENCENDIDO:
    metrica_estado.success(f"🟢 BOT ENCENDIDO | Analizando BingX [{TIMEFRAME}] esperando {UMBRAL}%...")
else:
    metrica_estado.warning("🔴 BOT APAGADO | El modo de trading automático está desactivado.")
    monitor_operacion.info("Enciende el bot en la barra lateral para comenzar a buscar entradas.")

if 'en_operacion' not in st.session_state:
    st.session_state.en_operacion = False
if 'detalles_operacion' not in st.session_state:
    st.session_state.detalles_operacion = {}

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
        
        # 1. Configurar Apalancamiento especificando la dirección (Exigido por BingX)
        params_leverage = {'side': direccion} # LONG o SHORT
        exchange.set_leverage(int(LEVERAGE), symbol, params=params_leverage)
        
        # 2. Orden de Entrada (Demo VST) - PARAMETRO CORREGIDO A 'amount'
        lado_entrada = 'buy' if direccion == 'LONG' else 'sell'
        params_entrada = {'marginType': 'VST'} 
        orden_entrada = exchange.create_market_order(symbol, lado_entrada, amount=cantidad, params=params_entrada)
        time.sleep(0.3)
        
        # 3. Orden de Trailing Stop - PARAMETRO CORREGIDO A 'amount'
        lado_salida = 'sell' if direccion == 'LONG' else 'buy'
        params_trailing = {
            'callbackRate': str(TRAILING_PERC / 100),
            'reduceOnly': True
        }
        orden_trailing = exchange.create_order(symbol, 'TRAILING_STOP_MARKET', lado_salida, amount=cantidad, params=params_trailing)
        
        # Guardar estado local
        st.session_state.detalles_operacion = {
            "Par": symbol.split('/')[0],
            "Dirección": direccion,
            "Precio Entrada": precio_actual,
            "Cantidad": cantidad,
            "Valor Nominal": f"${MARGEN_USD * LEVERAGE} USD"
        }
        
        msg = f"🛒 ¡POSICIÓN ABIERTA EN BINGX!\n\nPar: {symbol.split('/')[0]}\nDirección: {direccion}\nPrecio: {precio_actual} USDT\n🎯 Trailing Stop colocado al {TRAILING_PERC}%"
        enviar_alerta(msg)
        return True
    except Exception as e:
        consola_errores.error(f"❌ BingX rechazó la orden: {e}")
        return False

# =====================================================================
# MOTOR DE ESCANEO CONTINUO (BINGX)
# =====================================================================
if BOT_ENCENDIDO:
    PARES_A_REVISAR = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]

    if st.session_state.en_operacion:
        try:
            par_activo = st.session_state.detalles_operacion.get("Par") + "/USDT"
            posiciones = exchange.fetch_positions(symbols=[par_activo])
            if posiciones and float(posiciones[0]['info'].get('positionAmt', 0)) == 0:
                st.session_state.en_operacion = False
                enviar_alerta(f"🏁 La posición en {par_activo.split('/')[0]} ha sido cerrada.")
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
