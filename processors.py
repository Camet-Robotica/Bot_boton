"""processors.py — Lógica de negocio: procesamiento de notificaciones."""

import itertools
import logging
import threading
from datetime import datetime, timezone, timedelta

import cache
import config
import db
import sender
import formatters
from config import (
    CPU_TEMP_HARDWARE_ID,
    CPU_TEMP_SENSOR_ID,
    DESCONEXION_MIN_SEGUNDOS,
    DESCONEXION_REHIDRATACION_MAX,
    MARCAR_FALSAS_ALERTAS,
    MIN_CPU_FAN_SPEED,
)

log = logging.getLogger(__name__)

_AR = timezone(timedelta(hours=-3))

# Una normalización o una reconexión que quedó sin avisar y es más vieja que esto
# (segundos) ya no se manda: se cierra en la DB sin mensaje. Evita que un reinicio
# del bot mande avisos de hace horas o días.
ALERTA_VIEJA_SEGUNDOS = getattr(config, "ALERTA_VIEJA_SEGUNDOS", 1800)

# ── Timer de normalización ────────────────────────────────────────────────────
# Clave: (cliente, hardware_id, sensor_id)
# Valor: threading.Timer activo

_timers:      dict[tuple, threading.Timer] = {}
_timers_lock = threading.Lock()

# ── Periodo de gracia de desconexiones ────────────────────────────────────────
# Clave: cliente
# Valor: (token, threading.Timer, inicio_desconexion)
# El token identifica cada periodo de gracia y evita que un timer que ya venció
# emita la alerta si mientras tanto fue cancelado o reemplazado por otro.

_desconexiones:      dict[str, tuple] = {}
_desconexiones_lock = threading.Lock()
_token_seq           = itertools.count(1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _a_datetime_utc(valor):
    """Normaliza un timestamp (str o datetime) a datetime con tz UTC, o None."""
    if not valor:
        return None
    try:
        dt = valor if isinstance(valor, datetime) else datetime.fromisoformat(str(valor))
    except (TypeError, ValueError):
        log.warning("Timestamp no interpretable: %r", valor)
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)   # el VPS y la DB corren en UTC
    return dt


# ── Normalización de componentes ──────────────────────────────────────────────

def _on_normalizacion(key: tuple, datos: dict) -> None:
    """Callback: se ejecuta cuando venció la espera sin nuevas anomalías para una clave."""
    with _timers_lock:
        _timers.pop(key, None)

    try:
        # Enriquecer datos con la hora actual de normalización
        datos_norm = {**datos, "timestamp": datetime.now(tz=_AR).isoformat()}
        mensaje = formatters.msg_normalizado(datos_norm)
    except Exception:
        # Sin mensaje no se cierra nada: la alerta queda en 1 y se reintenta al reiniciar.
        log.exception("No se pudo construir el mensaje de normalización para %s", key)
        return

    if sender.enviar(mensaje):
        db.cerrar_alerta_componente(datos)
        log.info("✅ Normalización enviada para %s", key)
    else:
        log.error(
            "No se pudo enviar la normalización de %s: la alerta queda abierta "
            "y se reintentará en el próximo arranque.", key
        )


def _gestionar_timer(key: tuple, datos: dict) -> bool:
    """
    Cancela el timer existente (si hay) e inicia uno nuevo de la espera configurada.
    Retorna True si es la PRIMERA anomalía (no había timer previo).
    """
    with _timers_lock:
        es_primera = key not in _timers
        if key in _timers:
            _timers[key].cancel()

        tiempo_espera = cache.get_espera_normalizacion()
        t = threading.Timer(tiempo_espera, _on_normalizacion, args=(key, datos))
        t.daemon = True
        _timers[key] = t

    t.start()

    if es_primera:
        log.info("⏱️  Timer de normalización iniciado para %s", key)
    else:
        log.info("🔄 Timer reseteado para %s", key)

    return es_primera


# ── Desconexiones de clientes ─────────────────────────────────────────────────

def procesar_desconexion(datos: dict) -> None:
    """
    INSERT en auditoria_clientes → alerta de desconexión, con periodo de gracia.

    No se avisa nada hasta que la desconexión supere DESCONEXION_MIN_SEGUNDOS.
    Si el cliente vuelve antes de ese tiempo, el corte se descarta como falso
    positivo (pérdida momentánea de internet o desincronización entre el envío
    y la recepción de recursos) y no se manda ningún mensaje.
    """
    cliente = datos.get("cliente")
    if cliente is None:
        log.warning("procesar_desconexion: notificación sin cliente, se ignora.")
        return

    if DESCONEXION_MIN_SEGUNDOS <= 0:
        _emitir_desconexion(cliente, datos)   # filtro desactivado
        return

    _programar_desconexion(cliente, datos, DESCONEXION_MIN_SEGUNDOS)


def _programar_desconexion(cliente: str, datos: dict, espera: float) -> None:
    """Arranca (o retoma) el periodo de gracia de una desconexión."""
    inicio = datos.get("inicio_desconexion")
    token  = next(_token_seq)

    with _desconexiones_lock:
        anterior = _desconexiones.get(cliente)
        if anterior is not None:
            if anterior[2] == inicio:
                # Aviso duplicado del mismo corte: no reiniciar la cuenta, o el
                # periodo de gracia se estiraría indefinidamente.
                log.info("↩️  Desconexión duplicada de '%s': se mantiene el periodo de gracia en curso.", cliente)
                return
            anterior[1].cancel()
            log.info("♻️  Nueva desconexión de '%s': se reemplaza el periodo de gracia anterior.", cliente)

        t = threading.Timer(espera, _emitir_desconexion, args=(cliente, datos, token))
        t.daemon = True
        _desconexiones[cliente] = (token, t, inicio)

    t.start()
    log.info(
        "⏳ Desconexión de '%s' en periodo de gracia: se avisa si sigue caído en %d s.",
        cliente, int(espera),
    )


def _emitir_desconexion(cliente: str, datos: dict, token: int | None = None) -> None:
    """Confirma la desconexión: manda la alerta y la marca en la DB."""
    try:
        if token is not None:
            with _desconexiones_lock:
                actual = _desconexiones.get(cliente)
                if actual is None or actual[0] != token:
                    # Cancelado o reemplazado justo mientras el timer disparaba.
                    return
                del _desconexiones[cliente]

        log.info("🔴 Desconexión de '%s' confirmada (superó %d s).", cliente, DESCONEXION_MIN_SEGUNDOS)
        sender.enviar(formatters.msg_desconexion(datos))
        db.marcar_alerta_clientes(datos)
    except Exception:
        log.exception("Error al emitir la alerta de desconexión de '%s'", cliente)


def procesar_reconexion(datos: dict) -> None:
    """
    UPDATE en auditoria_clientes (fin_desconexion completado) → alerta de reconexión.

    Si el cliente todavía estaba en su periodo de gracia, el corte nunca se avisó:
    se cancela el timer y se descarta en silencio como falsa alerta.
    """
    cliente = datos.get("cliente")

    with _desconexiones_lock:
        pendiente = _desconexiones.pop(cliente, None)

    if pendiente is not None:
        pendiente[1].cancel()
        log.info(
            "🔇 Falsa alerta filtrada: '%s' se reconectó dentro de los %d s de gracia (duración=%s).",
            cliente, DESCONEXION_MIN_SEGUNDOS, datos.get("duracion"),
        )
        if MARCAR_FALSAS_ALERTAS:
            db.descartar_alerta_cliente(datos)
        return

    if sender.enviar(formatters.msg_reconexion(datos)):
        db.cerrar_alerta_cliente(datos)
    else:
        log.error(
            "No se pudo enviar la reconexión de '%s': la alerta queda abierta "
            "y se reintenta en la próxima vuelta de reintentos.", cliente
        )


# ── Componentes ───────────────────────────────────────────────────────────────

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

        if hardware_id == CPU_TEMP_HARDWARE_ID and sensor_id == CPU_TEMP_SENSOR_ID:
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


# ── Rehidratación tras un reinicio ────────────────────────────────────────────

def rehidratar_timers() -> None:
    """Busca anomalías pendientes en DB y restaura los timers o manda normalización si vencieron."""
    pendientes = db.obtener_alertas_pendientes()
    if not pendientes:
        log.info("No hay timers pendientes para rehidratar.")
        return

    tiempo_espera_total = cache.get_espera_normalizacion()
    ahora_utc = datetime.now(timezone.utc)
    rehidratados = 0

    for row in pendientes:
        cliente = row.get("cliente")
        hardware_id = row.get("hardware_id")
        sensor_id = row.get("sensor_id")

        ultimo_ts = _a_datetime_utc(row.get("ultimo_ts"))
        if ultimo_ts is None:
            continue

        key = (cliente, hardware_id, sensor_id)

        tiempo_transcurrido = (ahora_utc - ultimo_ts).total_seconds()
        tiempo_restante = tiempo_espera_total - tiempo_transcurrido

        datos_simulados = {
            "cliente": cliente,
            "hardware_id": hardware_id,
            "sensor_id": sensor_id,
            "timestamp": ultimo_ts.isoformat()
        }

        if -tiempo_restante > ALERTA_VIEJA_SEGUNDOS:
            log.info("🗄️  Rehidratación: normalización vieja de %s (pasaron %d s): se cierra sin avisar.", key, int(tiempo_transcurrido))
            db.cerrar_alerta_componente(datos_simulados)
        elif tiempo_restante <= 0:
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
        if _reconexion_vieja(row):
            continue
        # Si el cliente ya tiene un fin_desconexion, significa que se reconectó
        # pero el bot no estaba online para enviar el mensaje y cerrar la alerta.
        if row.get("fin_desconexion"):
            log.info("⌛ Rehidratación: Cliente '%s' reconectado previamente. Enviando alerta y cerrando.", row.get("cliente"))
            # procesar_reconexion enviará el mensaje a Telegram y pondrá alerta=2
            procesar_reconexion(row)
            rehidratados += 1

    if rehidratados > 0:
        log.info("✅ Se han rehidratado y notificado %d reconexiones de clientes pendientes.", rehidratados)


def _reconexion_vieja(row: dict) -> bool:
    """Si la reconexión pendiente es más vieja que ALERTA_VIEJA_SEGUNDOS, la cierra sin avisar."""
    fin = _a_datetime_utc(row.get("fin_desconexion"))
    if fin is None:
        return False
    antiguedad = (datetime.now(timezone.utc) - fin).total_seconds()
    if antiguedad <= ALERTA_VIEJA_SEGUNDOS:
        return False
    log.info("🗄️  Reconexión vieja de '%s' (hace %d s): se cierra sin avisar.", row.get("cliente"), int(antiguedad))
    db.cerrar_alerta_cliente(row)
    return True


def reintentar_reconexiones_pendientes(antiguedad_min: float = 300) -> None:
    """
    Reintenta las reconexiones cuyo mensaje no salió (alerta=1 con fin_desconexion).

    Corre cada tanto mientras el bot está andando, así un envío que falló no
    espera al próximo reinicio. Sólo toma las que se cerraron hace más de
    `antiguedad_min` segundos, para no pisarse con el aviso que el bot está
    mandando en ese momento.
    """
    pendientes = db.obtener_alertas_clientes_pendientes()
    if not pendientes:
        return

    ahora_utc = datetime.now(timezone.utc)
    for row in pendientes:
        fin = _a_datetime_utc(row.get("fin_desconexion"))
        if fin is None or (ahora_utc - fin).total_seconds() < antiguedad_min:
            continue
        if _reconexion_vieja(row):
            continue
        log.info("🔁 Reintento: reconexión de '%s' pendiente desde %s.", row.get("cliente"), fin.isoformat())
        procesar_reconexion(row)


def rehidratar_desconexiones() -> None:
    """
    Retoma los periodos de gracia truncados por un reinicio.

    Mira las desconexiones todavía abiertas y sin alertar (alerta=0, sin
    fin_desconexion) iniciadas dentro de DESCONEXION_REHIDRATACION_MAX y, según
    el tiempo transcurrido, avisa de inmediato o reprograma lo que resta de la
    gracia. La ventana evita una ráfaga de avisos viejos al arrancar.
    """
    if DESCONEXION_REHIDRATACION_MAX <= 0:
        return

    pendientes = db.obtener_desconexiones_sin_alertar()
    if not pendientes:
        return

    ahora_utc = datetime.now(timezone.utc)
    inmediatas = reprogramadas = 0

    for row in pendientes:
        cliente = row.get("cliente")
        inicio = _a_datetime_utc(row.get("inicio_desconexion"))
        if not cliente or inicio is None:
            continue

        transcurrido = (ahora_utc - inicio).total_seconds()
        if transcurrido > DESCONEXION_REHIDRATACION_MAX:
            log.info(
                "⏭️  Rehidratación: desconexión de '%s' fuera de la ventana (%d s), se ignora.",
                cliente, int(transcurrido),
            )
            continue

        restante = DESCONEXION_MIN_SEGUNDOS - transcurrido
        if restante <= 0:
            log.info(
                "⌛ Rehidratación: '%s' sigue desconectado hace %d s, alerta emitida ahora.",
                cliente, int(transcurrido),
            )
            _emitir_desconexion(cliente, row)
            inmediatas += 1
        else:
            _programar_desconexion(cliente, row, restante)
            reprogramadas += 1

    if inmediatas or reprogramadas:
        log.info(
            "✅ Rehidratación de desconexiones: %d alerta(s) emitida(s), %d periodo(s) de gracia restaurado(s).",
            inmediatas, reprogramadas,
        )
