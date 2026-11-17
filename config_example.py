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

# umbral_id de la tabla `umbrales` que guarda, en segundos, la espera de
# normalización. Si no existe se usa NORMALIZACION_ESPERA.
UMBRAL_ID_NORMALIZACION = 999

# ── Filtro de falsas desconexiones ────────────────────────────────────────────
# Una desconexión sólo se avisa si el cliente sigue caído después de este tiempo.
# Los cortes más breves (pérdida momentánea de internet, desincronización entre
# el envío y la recepción de recursos) se descartan sin notificar.
# Poner 0 desactiva el filtro y vuelve al comportamiento anterior (el filtro de
# la base, en procedures.py de LHM_app, ya espera silencio + confirmación).
DESCONEXION_MIN_SEGUNDOS = int(os.getenv("DESCONEXION_MIN_SEGUNDOS", 30))

# Al arrancar, el bot retoma los periodos de gracia que quedaron truncados por un
# reinicio. Sólo mira desconexiones iniciadas dentro de esta ventana (segundos),
# para no disparar una ráfaga de avisos viejos. Poner 0 desactiva la rehidratación.
DESCONEXION_REHIDRATACION_MAX = int(os.getenv("DESCONEXION_REHIDRATACION_MAX", 3600))

# Si es True, las falsas alertas descartadas se marcan en la DB con el estado
# ALERTA_ESTADO_DESCARTADA en vez de quedarse en 0 (útil para auditoría).
MARCAR_FALSAS_ALERTAS = os.getenv("MARCAR_FALSAS_ALERTAS", "false").lower() == "true"

# ── Estados de la columna `alerta` ────────────────────────────────────────────
ALERTA_ESTADO_SIN_ENVIAR = 0
ALERTA_ESTADO_ABIERTA    = 1  # alertado, esperando normalización / reconexión
ALERTA_ESTADO_CERRADA    = 2  # normalización o reconexión ya notificada
ALERTA_ESTADO_DESCARTADA = 3  # falsa alerta filtrada (requiere MARCAR_FALSAS_ALERTAS)

# ── Parámetros de Sensores ────────────────────────────────────────────────────
MIN_CPU_FAN_SPEED = 1500  # Velocidad mínima esperada del ventilador del CPU

CPU_TEMP_HARDWARE_ID = 0   # temperatura del CPU: dispara el chequeo del ventilador
CPU_TEMP_SENSOR_ID   = 18
CPU_FAN_HARDWARE_ID  = 2   # RPM del ventilador del CPU
CPU_FAN_SENSOR_ID    = 17
