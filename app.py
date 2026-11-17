"""app.py — Entry point del Bot de Alertas."""

import logging
import threading
import time

import cache
import config
import listener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Cada cuánto se reintentan las reconexiones cuyo mensaje no salió.
REINTENTO_PENDIENTES_SEGUNDOS = getattr(config, "REINTENTO_PENDIENTES_SEGUNDOS", 600)


def _reintentar_pendientes_periodicamente() -> None:
    import processors
    while True:
        time.sleep(REINTENTO_PENDIENTES_SEGUNDOS)
        try:
            processors.reintentar_reconexiones_pendientes()
        except Exception:
            log.exception("Error al reintentar reconexiones pendientes")


def main() -> None:
    log.info("=" * 60)
    log.info("  Bot de Alertas – LISTEN/NOTIFY → Telegram")
    log.info("=" * 60)

    # 1. Carga inicial del caché de tablas estáticas
    cache.cargar()

    # 2. Hilo demonio que refresca el caché cada hora
    cache.iniciar_refresco_periodico()

    # 3. Restaurar cronómetros, reconexiones y periodos de gracia pendientes
    import processors
    processors.rehidratar_timers()
    processors.rehidratar_clientes()
    processors.rehidratar_desconexiones()

    # 4. Hilo demonio que reintenta las reconexiones que no se pudieron avisar
    threading.Thread(target=_reintentar_pendientes_periodicamente, daemon=True,
                     name="reintentos").start()

    # 5. Bucle principal de escucha (bloqueante)
    listener.escuchar()


if __name__ == "__main__":
    main()