"""cache.py — Caché en memoria de las tablas estáticas sensor y componente."""

import logging
import threading
import time

import psycopg2
from db import get_connection
from config import CACHE_TTL_SEGUNDOS

log = logging.getLogger(__name__)

_cache_sensores:    dict[int, dict] = {}   # sensor_id   → {sensor_id, sensor_name, sensor_type}
_cache_componentes: dict[int, dict] = {}   # hardware_id → {hardware_id, hardware_type}
_cache_umbrales:    dict[int, int] = {}   # umbral_id   → {umbral_id, sensor_id, umbral_max}
_lock = threading.Lock()


def cargar() -> None:
    """Descarga sensor y componente de la DB y los guarda en memoria."""
    global _cache_sensores, _cache_componentes, _cache_umbrales
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT sensor_id, sensor_name, sensor_type FROM sensor;")
                cols = [d.name for d in cur.description]
                sensores = {row[0]: dict(zip(cols, row)) for row in cur.fetchall()}

                cur.execute("SELECT hardware_id, hardware_type FROM componente;")
                cols = [d.name for d in cur.description]
                componentes = {row[0]: dict(zip(cols, row)) for row in cur.fetchall()}

                cur.execute("SELECT umbral_id, sensor_id, umbral_max FROM umbrales;")
                cols = [d.name for d in cur.description]
                umbrales = {row[0]: dict(zip(cols, row)) for row in cur.fetchall()}

        with _lock:
            _cache_sensores    = sensores
            _cache_componentes = componentes
            _cache_umbrales    = umbrales

        log.info("✅ Caché: %d sensores, %d componentes, %d umbrales.", len(sensores), len(componentes), len(umbrales))
    except Exception as exc:
        log.error("Error al cargar caché: %s", exc)


def get_sensor(sensor_id) -> dict:
    with _lock:
        return _cache_sensores.get(sensor_id, {})


def get_componente(hardware_id) -> dict:
    with _lock:
        return _cache_componentes.get(hardware_id, {})


def get_umbral(umbral_id) -> float | None:
    """Retorna el valor umbral_max para un umbral_id dado, o None si no existe."""
    with _lock:
        entrada = _cache_umbrales.get(umbral_id)
        return entrada["umbral_max"] if entrada else None


def iniciar_refresco_periodico() -> None:
    """Lanza un hilo demonio que recarga el caché cada CACHE_TTL_SEGUNDOS."""
    def _loop():
        while True:
            time.sleep(CACHE_TTL_SEGUNDOS)
            log.info("🔄 Refrescando caché…")
            cargar()

    threading.Thread(target=_loop, daemon=True, name="cache-refresh").start()
