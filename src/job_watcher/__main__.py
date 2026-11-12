"""Punto de entrada del bot."""

from __future__ import annotations

import sys

from loguru import logger

from job_watcher.config import load_config
from job_watcher.notifier import TelegramError, TelegramNotifier


def main() -> int:
    """Entrypoint ejecutado con python -m job_watcher."""
    config = load_config()
    logger.remove()
    logger.add(
        sys.stderr,
        level=config.app.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
            "<level>{message}</level>"
        ),
    )

    logger.info(
        "Configuracion cargada (perfiles: {})",
        [p.name for p in config.profiles],
    )

    notifier = TelegramNotifier(
        bot_token=config.telegram.bot_token,
        chat_id=config.telegram.chat_id,
        parse_mode=config.telegram.parse_mode,
        disable_web_page_preview=config.telegram.disable_web_page_preview,
    )

    try:
        notifier.send(
            "Job Watcher - Sprint 0\nEl bot esta conectado y listo para recibir notificaciones."
        )
    except TelegramError:
        logger.exception("No se pudo enviar el mensaje de prueba")
        return 1

    logger.success("Mensaje de prueba enviado a Telegram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
