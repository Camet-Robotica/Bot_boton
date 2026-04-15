"""listener.py — Bucle LISTEN/NOTIFY con reconexión automática."""

import json
import logging
import select
import time

import psycopg2

import processors
from config import CANALES, RECONEXION_ESPERA
from db import get_connection

log = logging.getLogger(__name__)


def _despachar_cliente(datos: dict) -> None:
    """
    Distingue entre desconexión (fin_desconexion ausente/null)
    y reconexión (fin_desconexion presente).
    Ambas notificaciones llegan por el canal alertas_clientes.
    """
    if datos.get("fin_desconexion"):
        processors.procesar_reconexion(datos)
    else:
        processors.procesar_desconexion(datos)


# Tabla de despacho: canal → función procesadora
_CANAL_HANDLERS = {
    "alertas_clientes":    _despachar_cliente,
    "alertas_componentes": processors.procesar_componente,
}


def _despachar(canal: str, payload_raw: str) -> None:
    try:
        datos = json.loads(payload_raw)
    except json.JSONDecodeError:
        log.warning("Payload no es JSON válido (%.200s)", payload_raw)
        return

    handler = _CANAL_HANDLERS.get(canal)
    if handler:
        handler(datos)
    else:
        log.warning("Canal desconocido: %s", canal)


def escuchar() -> None:
    """Conexión persistente a Postgres. Reconecta automáticamente ante errores."""
    while True:
        conn = None
        try:
            log.info("Conectando a la base de datos…")
            conn = get_connection(autocommit=True)
            cur = conn.cursor()

            for canal in CANALES:
                cur.execute(f"LISTEN {canal};")
                log.info("📡 Escuchando canal: %s", canal)

            log.info("🟢 Listo. Esperando notificaciones… (Ctrl+C para salir)")

            while True:
                # select() bloquea hasta que haya datos o pasen 30 s (heartbeat)
                listo, _, _ = select.select([conn], [], [], 30)
                if listo:
                    conn.poll()
                    while conn.notifies:
                        notif = conn.notifies.pop(0)
                        log.info("📨 canal=%s pid=%s", notif.channel, notif.pid)
                        _despachar(notif.channel, notif.payload)
                else:
                    cur.execute("SELECT 1")   # heartbeat anti-timeout

        except psycopg2.OperationalError as exc:
            log.error("Conexión perdida: %s", exc)
        except KeyboardInterrupt:
            log.info("Detenido por el usuario.")
            break
        except Exception as exc:
            log.exception("Error inesperado: %s", exc)
        finally:
            if conn and not conn.closed:
                try:
                    conn.close()
                except Exception:
                    pass

        log.info("Reconectando en %d s…", RECONEXION_ESPERA)
        time.sleep(RECONEXION_ESPERA)
