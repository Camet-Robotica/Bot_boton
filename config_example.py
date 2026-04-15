"""config.py — Constantes globales de la aplicación."""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_CHAT_IDS: list[int] = [
    ## Agregar los chat ids de los usuarios
]
TELEGRAM_BOT_CODE: str = os.getenv("TELEGRAM_BOT_CODE", "alerta_bot")
TELEGRAM_API_URL: str  = os.getenv("TELEGRAM_API_URL", "")

# ── Base de datos ─────────────────────────────────────────────────────────────
DB_DSN: dict = dict(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS"),
)

# ── Canales LISTEN/NOTIFY ─────────────────────────────────────────────────────
CANALES = ["alertas_clientes", "alertas_componentes"]

# ── Timings ───────────────────────────────────────────────────────────────────
RECONEXION_ESPERA    = 10     # segundos entre reintentos de conexión DB
CACHE_TTL_SEGUNDOS   = 1800  # frecuencia de refresco del caché estático
NORMALIZACION_ESPERA = 3600  # tiempo sin anomalías para declarar normalización

# ── Parámetros de Sensores ────────────────────────────────────────────────────
MIN_CPU_FAN_SPEED = 1500  # Velocidad mínima esperada del ventilador del CPU
