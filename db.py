"""db.py — Conexión a la base de datos y operaciones de escritura."""

import logging
from contextlib import closing

import psycopg2
from psycopg2 import sql

from config import (
    ALERTA_ESTADO_DESCARTADA,
    CPU_FAN_HARDWARE_ID,
    CPU_FAN_SENSOR_ID,
    DB_DSN,
)

log = logging.getLogger(__name__)


def get_connection(autocommit: bool = False) -> psycopg2.extensions.connection:
    """Abre y retorna una conexión a Postgres."""
    conn = psycopg2.connect(**DB_DSN)
    if autocommit:
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


# ── Helpers internos ──────────────────────────────────────────────────────────

def _ejecutar_update(sql_text, params: tuple, descripcion: str) -> int:
    """Ejecuta un UPDATE con commit y manejo de errores. Retorna las filas afectadas."""
    try:
        # `with conn` sólo abre/cierra la transacción: la conexión hay que cerrarla aparte.
        with closing(get_connection()) as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql_text, params)
                    filas = cur.rowcount
        log.info("🔖 %s → %d fila(s) actualizada(s)", descripcion, filas)
        return filas
    except Exception as exc:
        log.error("Error al actualizar %s: %s", descripcion, exc)
        return 0


def _ejecutar_select(sql_text, params: tuple | None = None, descripcion: str = "consulta") -> list[dict]:
    """Ejecuta un SELECT y retorna las filas como lista de diccionarios."""
    resultados: list[dict] = []
    try:
        with closing(get_connection()) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_text, params)
                cols = [d.name for d in cur.description]
                resultados = [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as exc:
        log.error("Error en %s: %s", descripcion, exc)
    return resultados


# ── Clientes ──────────────────────────────────────────────────────────────────

def marcar_alerta_clientes(datos: dict) -> None:
    """
    Marca alerta=1 en auditoria_clientes.
    Clave única: inicio_desconexion + cliente.
    """
    ts      = datos.get("inicio_desconexion")
    cliente = datos.get("cliente")
    if ts is None or cliente is None:
        log.warning("marcar_alerta_clientes: faltan campos clave (ts=%s, cliente=%s).", ts, cliente)
        return
    _ejecutar_update(
        """
        UPDATE auditoria_clientes
           SET alerta = 1
         WHERE inicio_desconexion = %s
           AND cliente = %s
           AND alerta  = 0
        """,
        (ts, cliente),
        f"auditoria_clientes (cliente={cliente})",
    )


def obtener_alertas_clientes_pendientes() -> list[dict]:
    """Obtiene los registros con alerta=1 de clientes."""
    return _ejecutar_select(
        """
        SELECT cliente, inicio_desconexion, fin_desconexion, duracion
          FROM auditoria_clientes
         WHERE alerta = 1
        """,
        descripcion="alertas de clientes pendientes",
    )


def obtener_desconexiones_sin_alertar() -> list[dict]:
    """
    Desconexiones todavía abiertas (sin fin_desconexion) que nunca generaron alerta.
    Sirven para retomar el periodo de gracia tras un reinicio del bot.
    """
    return _ejecutar_select(
        """
        SELECT cliente, inicio_desconexion
          FROM auditoria_clientes
         WHERE alerta = 0
           AND fin_desconexion IS NULL
        """,
        descripcion="desconexiones sin alertar",
    )


def cerrar_alerta_cliente(datos: dict) -> None:
    """Cambia alerta=1 a alerta=2 para indicar que se notificó la reconexión."""
    cliente = datos.get("cliente")
    inicio  = datos.get("inicio_desconexion")

    if cliente is None:
        log.warning("cerrar_alerta_cliente: faltan campos clave.")
        return

    if inicio is not None:
        # Cierra sólo la desconexión concreta, no todas las abiertas del cliente.
        _ejecutar_update(
            """
            UPDATE auditoria_clientes
               SET alerta = 2
             WHERE cliente = %s
               AND inicio_desconexion = %s
               AND alerta = 1
            """,
            (cliente, inicio),
            f"auditoria_clientes_cierre (cliente={cliente}, inicio={inicio})",
        )
        return

    _ejecutar_update(
        """
        UPDATE auditoria_clientes
           SET alerta = 2
         WHERE cliente = %s
           AND alerta = 1
        """,
        (cliente,),
        f"auditoria_clientes_cierre (cliente={cliente})",
    )


def descartar_alerta_cliente(datos: dict) -> None:
    """
    Marca una desconexión como falsa alerta filtrada.
    Sólo se invoca si MARCAR_FALSAS_ALERTAS está activo.
    """
    cliente = datos.get("cliente")
    inicio  = datos.get("inicio_desconexion")

    if cliente is None or inicio is None:
        log.warning("descartar_alerta_cliente: faltan campos clave.")
        return
    _ejecutar_update(
        """
        UPDATE auditoria_clientes
           SET alerta = %s
         WHERE cliente = %s
           AND inicio_desconexion = %s
           AND alerta = 0
        """,
        (ALERTA_ESTADO_DESCARTADA, cliente, inicio),
        f"auditoria_clientes_descarte (cliente={cliente})",
    )


# ── Componentes ───────────────────────────────────────────────────────────────

def marcar_alerta_componente(datos: dict) -> None:
    """
    Marca alerta=1 en auditoria_componente.
    Clave única: timestamp + cliente + hardware_id + sensor_id.
    """
    ts          = datos.get("timestamp")
    cliente     = datos.get("cliente")
    hardware_id = datos.get("hardware_id")
    sensor_id   = datos.get("sensor_id")

    if any(v is None for v in (ts, cliente, hardware_id, sensor_id)):
        log.warning("marcar_alerta_componente: faltan campos clave.")
        return
    _ejecutar_update(
        """
        UPDATE auditoria_componente
           SET alerta = 1
         WHERE timestamp   = %s
           AND cliente     = %s
           AND hardware_id = %s
           AND sensor_id   = %s
           AND alerta      = 0
        """,
        (ts, cliente, hardware_id, sensor_id),
        f"auditoria_componente (cliente={cliente}, hw={hardware_id}, sensor={sensor_id})",
    )


def obtener_alertas_pendientes() -> list[dict]:
    """Obtiene los registros con alerta=1 más recientes agrupados por componente."""
    return _ejecutar_select(
        """
        SELECT cliente, hardware_id, sensor_id, MAX(timestamp) as ultimo_ts
          FROM auditoria_componente
         WHERE alerta = 1
         GROUP BY cliente, hardware_id, sensor_id
        """,
        descripcion="alertas de componentes pendientes",
    )


def cerrar_alerta_componente(datos: dict) -> None:
    """Cambia alerta=1 a alerta=2 para indicar que se notificó la normalización."""
    cliente     = datos.get("cliente")
    hardware_id = datos.get("hardware_id")
    sensor_id   = datos.get("sensor_id")

    if any(v is None for v in (cliente, hardware_id, sensor_id)):
        log.warning("cerrar_alerta_componente: faltan campos clave.")
        return
    _ejecutar_update(
        """
        UPDATE auditoria_componente
           SET alerta = 2
         WHERE cliente = %s
           AND hardware_id = %s
           AND sensor_id = %s
           AND alerta = 1
        """,
        (cliente, hardware_id, sensor_id),
        f"auditoria_componente_cierre (cliente={cliente}, hw={hardware_id}, sensor={sensor_id})",
    )


def obtener_velocidad_ventilador_cpu(cliente: str, ts: str) -> float | None:
    """Obtiene la velocidad del ventilador del CPU para un cliente y timestamp
    específicos, o el valor inmediatamente anterior."""
    if not cliente or not ts:
        return None

    try:
        with closing(get_connection()) as conn:
            with conn.cursor() as cur:
                # El nombre de la tabla es el del cliente: va como identificador
                # escapado por psycopg2, nunca interpolado a mano.
                query = sql.SQL(
                    """
                    SELECT "value" FROM {tabla}
                     WHERE hardware_id = %s AND sensor_id = %s AND timestamp <= %s
                     ORDER BY timestamp DESC
                     LIMIT 1
                    """
                ).format(tabla=sql.Identifier(cliente))
                cur.execute(query, (CPU_FAN_HARDWARE_ID, CPU_FAN_SENSOR_ID, ts))
                row = cur.fetchone()
                if row and row[0] is not None:
                    return float(row[0])
    except Exception as exc:
        log.error("Error al obtener ventilador de cpu para %s: %s", cliente, exc)
    return None
