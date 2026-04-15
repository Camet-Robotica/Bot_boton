"""processors.py — Lógica de negocio: procesamiento de notificaciones."""

import logging
import threading
from datetime import datetime, timezone, timedelta
import cache
import db
import sender
import formatters
from config import NORMALIZACION_ESPERA
from config import MIN_CPU_FAN_SPEED

log = logging.getLogger(__name__)

# ── Timer de normalización ────────────────────────────────────────────────────
# Clave: (cliente, hardware_id, sensor_id)
# Valor: threading.Timer activo

_timers:      dict[tuple, threading.Timer] = {}
_timers_lock = threading.Lock()


def _on_normalizacion(key: tuple, datos: dict) -> None:
    """Callback: se ejecuta cuando venció 1h sin nuevas anomalías para una clave."""
    with _timers_lock:
        _timers.pop(key, None)

    # Enriquecer datos con la hora actual de normalización
    datos_norm = {
        **datos,
        "timestamp": datetime.now(tz=timezone(timedelta(hours=-3))).isoformat(),
    }
    db.cerrar_alerta_componente(datos)
    sender.enviar(formatters.msg_normalizado(datos_norm))
    log.info("✅ Normalización enviada para %s", key)


def _gestionar_timer(key: tuple, datos: dict) -> bool:
    """
    Cancela el timer existente (si hay) e inicia uno nuevo de NORMALIZACION_ESPERA segundos.
    Retorna True si es la PRIMERA anomalía (no había timer previo).
    """
    with _timers_lock:
        es_primera = key not in _timers
        if key in _timers:
            _timers[key].cancel()

        tiempo_espera = int(cache.get_umbral(999) or NORMALIZACION_ESPERA)
        t = threading.Timer(tiempo_espera, _on_normalizacion, args=(key, datos))
        t.daemon = True
        _timers[key] = t

    t.start()

    if es_primera:
        log.info("⏱️  Timer de normalización iniciado para %s", key)
    else:
        log.info("🔄 Timer reseteado para %s", key)

    return es_primera


# ── Procesadores públicos ─────────────────────────────────────────────────────

def procesar_desconexion(datos: dict) -> None:
    """INSERT en auditoria_clientes → alerta de desconexión."""
    sender.enviar(formatters.msg_desconexion(datos))
    db.marcar_alerta_clientes(datos)


def procesar_reconexion(datos: dict) -> None:
    """UPDATE en auditoria_clientes (fin_desconexion completado) → alerta de reconexión."""
    sender.enviar(formatters.msg_reconexion(datos))
    db.cerrar_alerta_cliente(datos)


def procesar_componente(datos: dict) -> None:
    """
    INSERT en auditoria_componente → lógica de umbral + timer de normalización.

    - Primera anomalía del período: envía alerta y arranca timer.
    - Anomalías siguientes dentro del período: resetea el timer (sin re-alertar).
    - En cualquier caso: marca alerta=1 en DB.
    """
    cliente = datos.get("cliente")
    hardware_id = datos.get("hardware_id")
    sensor_id = datos.get("sensor_id")
    ts = datos.get("timestamp")
    key = (cliente, hardware_id, sensor_id)

    db.marcar_alerta_componente(datos)
    es_primera = _gestionar_timer(key, datos)

    if es_primera:
        sender.enviar(formatters.msg_umbral_superado(datos))
        
        if hardware_id == 0 and sensor_id == 18:
            rpm = db.obtener_velocidad_ventilador_cpu(cliente, ts)
            if rpm is not None:
                if rpm > MIN_CPU_FAN_SPEED:
                    log.info("Ventilador CPU en %s RPM (>%s), temp cpu continúa funcionando normal.", rpm, MIN_CPU_FAN_SPEED)
                else:
                    log.warning("Ventilador CPU bajo para %s: %s RPM", cliente, rpm)
                    sender.enviar(formatters.msg_ventilador_cpu_bajo({
                        "cliente": cliente,
                        "timestamp": ts,
                        "rpm": rpm,
                        "min_rpm": MIN_CPU_FAN_SPEED
                    }))
    else:
        log.info("ℹ️  Anomalía adicional para %s — timer reseteado, sin re-alertar.", key)


def rehidratar_timers() -> None:
    """Busca anomalías pendientes en DB y restaura los timers o manda normalización si vencieron."""
    pendientes = db.obtener_alertas_pendientes()
    if not pendientes:
        log.info("No hay timers pendientes para rehidratar.")
        return

    tiempo_espera_total = int(cache.get_umbral(999) or NORMALIZACION_ESPERA)
    ahora_utc = datetime.now(timezone.utc)
    rehidratados = 0

    for row in pendientes:
        cliente = row.get("cliente")
        hardware_id = row.get("hardware_id")
        sensor_id = row.get("sensor_id")
        ultimo_ts_raw = row.get("ultimo_ts")

        if not ultimo_ts_raw:
            continue

        key = (cliente, hardware_id, sensor_id)
        
        # Parse or cast timestamp
        if isinstance(ultimo_ts_raw, str):
            ultimo_ts = datetime.fromisoformat(ultimo_ts_raw)
        else:
            ultimo_ts = ultimo_ts_raw

        if ultimo_ts.tzinfo is None:
            ultimo_ts = ultimo_ts.replace(tzinfo=timezone.utc)

        tiempo_transcurrido = (ahora_utc - ultimo_ts).total_seconds()
        tiempo_restante = tiempo_espera_total - tiempo_transcurrido

        datos_simulados = {
            "cliente": cliente,
            "hardware_id": hardware_id,
            "sensor_id": sensor_id,
            "timestamp": ultimo_ts.isoformat()
        }

        if tiempo_restante <= 0:
            log.info("⌛ Rehidratación: Normalización atrasada enviada para %s (pasaron %d s)", key, int(tiempo_transcurrido))
            _on_normalizacion(key, datos_simulados)
        else:
            with _timers_lock:
                if key not in _timers:
                    t = threading.Timer(tiempo_restante, _on_normalizacion, args=(key, datos_simulados))
                    t.daemon = True
                    _timers[key] = t
                    t.start()
                    rehidratados += 1
                    log.info("⏳ Rehidratación: Restaurado timer para %s (faltan %d s)", key, int(tiempo_restante))
    
    if rehidratados > 0:
        log.info("✅ Se han rehidratado %d timers de normalización remanentes.", rehidratados)


def rehidratar_clientes() -> None:
    """Busca alertas de clientes pendientes (alerta=1) y envía alerta de reconexión si ya se reconectaron."""
    pendientes = db.obtener_alertas_clientes_pendientes()
    if not pendientes:
        return
    
    rehidratados = 0
    for row in pendientes:
        # Si el cliente ya tiene un fin_desconexion, significa que se reconectó 
        # pero el bot no estaba online para enviar el mensaje y cerrar la alerta.
        if row.get("fin_desconexion"):
            log.info("⌛ Rehidratación: Cliente '%s' reconectado previamente. Enviando alerta y cerrando.", row.get("cliente"))
            # procesar_reconexion enviará el mensaje a Telegram y pondrá alerta=2
            procesar_reconexion(row)
            rehidratados += 1
            
    if rehidratados > 0:
        log.info("✅ Se han rehidratado y notificado %d reconexiones de clientes pendientes.", rehidratados)

