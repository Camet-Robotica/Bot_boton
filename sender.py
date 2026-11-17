"""sender.py — Envío de mensajes al bot de Telegram."""

import logging
import time

import requests

import config
from config import TELEGRAM_API_URL, TELEGRAM_BOT_CODE, TELEGRAM_CHAT_IDS

log = logging.getLogger(__name__)

# Reintentos ante un error de red, un timeout o una respuesta 429/5xx de la API.
# La API de Telegram deduplica /api/send (mismo bot, chats y mensaje): reintentar
# un envío que en realidad salió no duplica el mensaje.
INTENTOS = getattr(config, "ENVIO_INTENTOS", 3)
ESPERAS  = getattr(config, "ENVIO_ESPERAS", (5, 20))   # segundos antes del 2.º y del 3.er intento
TIMEOUT  = getattr(config, "ENVIO_TIMEOUT", 20)        # segundos por intento


def enviar(mensaje: str) -> bool:
    """
    Envía el mensaje a todos los chat_ids configurados en una sola llamada.
    Si falla por red, timeout o un error 429/5xx, reintenta hasta INTENTOS veces.
    Retorna True sólo si el envío fue aceptado: quien llama decide si cierra
    la alerta en la DB o la deja abierta para reintentarla.
    """
    if not TELEGRAM_API_URL:
        log.error("TELEGRAM_API_URL no definida en .env")
        return False

    body = {
        "bot_code":   TELEGRAM_BOT_CODE,
        "chat_ids":   TELEGRAM_CHAT_IDS,
        "message":    mensaje,
        "parse_mode": "Markdown",
    }
    for intento in range(1, INTENTOS + 1):
        try:
            resp = requests.post(TELEGRAM_API_URL, json=body, timeout=TIMEOUT)
            if resp.ok:
                if intento > 1:
                    log.info("✉️  Mensaje enviado en el intento %d de %d", intento, INTENTOS)
                else:
                    log.info("✉️  Mensaje enviado a %d chats", len(TELEGRAM_CHAT_IDS))
                return True
            log.warning(
                "Error HTTP %s al enviar (intento %d de %d): %s",
                resp.status_code, intento, INTENTOS, resp.text[:200],
            )
            if resp.status_code != 429 and resp.status_code < 500:
                return False   # error del pedido: reintentar no lo arregla
        except requests.RequestException as exc:
            log.error("Excepción al enviar mensaje (intento %d de %d): %s", intento, INTENTOS, exc)

        if intento < INTENTOS:
            time.sleep(ESPERAS[min(intento - 1, len(ESPERAS) - 1)])
    return False
