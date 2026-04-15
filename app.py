"""app.py — Entry point del Bot de Alertas."""

import logging

import cache
import listener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    log.info("=" * 60)
    log.info("  Bot de Alertas – LISTEN/NOTIFY → Telegram")
    log.info("=" * 60)

    # 1. Carga inicial del caché de tablas estáticas
    cache.cargar()

    # 2. Hilo demonio que refresca el caché cada hora
    cache.iniciar_refresco_periodico()

    # 3. Restaurar cronómetros pendientes en estado 1 y reconexiones pendientes
    import processors
    processors.rehidratar_timers()
    processors.rehidratar_clientes()

    # 4. Bucle principal de escucha (bloqueante)
    listener.escuchar()


if __name__ == "__main__":
    main()