"""db.py — Conexión a la base de datos y operaciones de escritura."""

import logging
import psycopg2
from config import DB_DSN

log = logging.getLogger(__name__)


def get_connection(autocommit: bool = False) -> psycopg2.extensions.connection:
    """Abre y retorna una conexión a Postgres."""
    conn = psycopg2.connect(**DB_DSN)
    if autocommit:
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


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


def _ejecutar_update(sql: str, params: tuple, descripcion: str) -> None:
    """Helper interno: ejecuta un UPDATE con commit y manejo de errores."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        log.info("🔖 alerta=1 marcado en %s", descripcion)
    except Exception as exc:
        log.error("Error al marcar alerta en %s: %s", descripcion, exc)


def obtener_alertas_pendientes() -> list[dict]:
    """Obtiene los registros con alerta=1 más recientes agrupados por componente."""
    resultados = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT cliente, hardware_id, sensor_id, MAX(timestamp) as ultimo_ts
                    FROM auditoria_componente
                    WHERE alerta = 1
                    GROUP BY cliente, hardware_id, sensor_id
                    """
                )
                cols = [d.name for d in cur.description]
                for row in cur.fetchall():
                    resultados.append(dict(zip(cols, row)))
    except Exception as exc:
        log.error("Error al obtener alertas pendientes: %s", exc)
    return resultados


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
    """Obtiene la velocidad del ventilador del CPU (hardware_id=2, sensor_id=17) 
    para un cliente y timestamp específicos o el valor inmediatamente anterior."""
    if not cliente or not ts:
        return None
        
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                tabla_segura = cliente.replace('"', '""')
                query = f"""
                    SELECT "value" FROM "{tabla_segura}"
                    WHERE hardware_id = 2 AND sensor_id = 17 AND timestamp <= %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """
                cur.execute(query, (ts,))
                row = cur.fetchone()
                if row:
                    return float(row[0])
    except Exception as exc:
        log.error("Error al obtener ventilador de cpu para %s: %s", cliente, exc)
    return None


def obtener_alertas_clientes_pendientes() -> list[dict]:
    """Obtiene los registros con alerta=1 de clientes."""
    resultados = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT cliente, inicio_desconexion, fin_desconexion, duracion
                    FROM auditoria_clientes
                    WHERE alerta = 1
                    """
                )
                cols = [d.name for d in cur.description]
                for row in cur.fetchall():
                    resultados.append(dict(zip(cols, row)))
    except Exception as exc:
        log.error("Error al obtener alertas de clientes pendientes: %s", exc)
    return resultados


def cerrar_alerta_cliente(datos: dict) -> None:
    """Cambia alerta=1 a alerta=2 para indicar que se notificó la reconexión."""
    cliente = datos.get("cliente")

    if cliente is None:
        log.warning("cerrar_alerta_cliente: faltan campos clave.")
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
