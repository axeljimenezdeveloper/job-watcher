"""Punto de entrada del bot."""

from __future__ import annotations

import sys

from loguru import logger

from job_watcher.config import load_config
from job_watcher.pipeline import run_pipeline


def main() -> int:
    """Entrypoint: python -m job_watcher."""
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
        "Iniciando Job Watcher (perfiles: {})",
        [p.name for p in config.profiles if p.enabled],
    )

    stats = run_pipeline(config)

    logger.info(
        "Resumen: scrapeadas={} nuevas={} matched={} notificadas={} errores={}",
        stats.scraped,
        stats.new,
        stats.matched,
        stats.notified,
        len(stats.errors),
    )

    if stats.errors:
        for err in stats.errors:
            logger.warning("Error: {}", err)

    return 0


if __name__ == "__main__":
    sys.exit(main())
