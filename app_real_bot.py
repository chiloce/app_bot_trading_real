import streamlit as st
import ccxt
import pandas as pd
import time
import requests

# 1. Configuración de la página (DEBE SER LO PRIMERO)
st.set_page_config(page_title="Crypto Execution Bot (BingX)", layout="wide")
st.title("⚡ Bot de Ejecución Automatizada (BingX)")
st.subheader("Entradas automáticas con Trailing Stop guiado")

# 2. Configuración de la barra lateral (Aquí es donde se crea la variable)
st.sidebar.header("⚙️ Parámetros de Trading")

# ¡AQUÍ SE DEFINE LA VARIABLE!
BOT_ENCENDIDO = st.sidebar.toggle("🤖 ACTIVAR BOT DE TRADING", value=False) 

TIMEFRAME = st.sidebar.selectbox("Temporalidad de Análisis", ["15m", "4h"], index=0)
UMBRAL = st.sidebar.slider("Umbral de Disparo (%)", min_value=0.01, max_value=5.0, value=0.10, step=0.01)
MARGEN_USD = st.sidebar.number_input("Margen de Entrada (USD)", min_value=1.0, value=5.0, step=1.0)
LEVERAGE = st.sidebar.number_input("Apalancamiento (X)", min_value=1, max_value=25, value=10, step=1)
VOLUMEN_MINIMO = st.sidebar.number_input("Volumen mínimo en vela (USDT)", value=10000, step=5000)
TRAILING_PERC = st.sidebar.slider("Trailing Stop (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)

# =====================================================================
# CONEXIÓN NATIVA A BINGX CON SANDBOX FORZADO 
# =====================================================================
# ... (El resto de tu código de conexión y funciones va aquí abajo)
