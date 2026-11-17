"""sender.py — Envío de mensajes al bot de Telegram."""

import logging
import requests
from config import TELEGRAM_API_URL, TELEGRAM_BOT_CODE, TELEGRAM_CHAT_IDS

log = logging.getLogger(__name__)


def enviar(mensaje: str) -> bool:
    """
    Envía el mensaje a todos los chat_ids configurados en una sola llamada.
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
    try:
        resp = requests.post(TELEGRAM_API_URL, json=body, timeout=10)
        if resp.ok:
            log.info("✉️  Mensaje enviado a %s", TELEGRAM_CHAT_IDS)
            return True
        log.warning(
            "Error HTTP %s al enviar: %s",
            resp.status_code, resp.text[:200],
        )
        return False
    except requests.RequestException as exc:
        log.error("Excepción al enviar mensaje: %s", exc)
        return False
