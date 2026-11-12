"""Monitoreo de salud de scrapers (deteccion de caidas)."""

from __future__ import annotations

from loguru import logger

from job_watcher.db import JobDatabase
from job_watcher.notifier import TelegramError, TelegramNotifier

DEFAULT_DROP_THRESHOLD = 0.5
DEFAULT_MIN_HISTORY_RUNS = 5


def should_alert(
    current_count: int,
    baseline_avg: float,
    last_count: int | None,
    history_runs: int,
    min_history_runs: int = DEFAULT_MIN_HISTORY_RUNS,
    drop_threshold: float = DEFAULT_DROP_THRESHOLD,
) -> bool:
    """True si el portal cayo mas del umbral y es la primera caida.

    Anti-spam: si ya habia caido en el ciclo anterior, no volver a alertar.
    """
    if history_runs < min_history_runs:
        return False
    if baseline_avg <= 0:
        return False
    cutoff = baseline_avg * (1 - drop_threshold)
    if current_count >= cutoff:
        return False
    return not (last_count is not None and last_count < cutoff)


def format_alert(portal: str, current: int, baseline_avg: float, runs: int) -> str:
    """Mensaje HTML para Telegram."""
    return (
        f"[!] <b>Alerta de scraper</b>\\n"
        f"Portal: <code>{portal}</code>\\n"
        f"Ofertas actuales: {current}\\n"
        f"Baseline ({runs} ciclos previos): {baseline_avg:.0f}\\n"
        f"Posible cambio de HTML o portal caido."
    )


def check_and_alert(
    portal: str,
    current_count: int,
    db: JobDatabase,
    notifier: TelegramNotifier,
    min_history_runs: int = DEFAULT_MIN_HISTORY_RUNS,
    drop_threshold: float = DEFAULT_DROP_THRESHOLD,
) -> bool:
    """Evalua y envia alerta si aplica. Retorna True si envio alerta."""
    baseline = db.get_scrape_baseline(portal)
    if baseline is None:
        return False
    runs, avg = baseline
    last_count = db.get_last_scraped(portal)
    if not should_alert(
        current_count=current_count,
        baseline_avg=avg,
        last_count=last_count,
        history_runs=runs,
        min_history_runs=min_history_runs,
        drop_threshold=drop_threshold,
    ):
        return False
    text = format_alert(portal, current_count, avg, runs)
    try:
        notifier.send(text)
    except TelegramError as exc:
        logger.error("No se pudo enviar alerta de {}: {}", portal, exc)
        return False
    logger.warning(
        "[{}] ALERTA: {} ofertas vs baseline {:.0f} ({} runs)",
        portal,
        current_count,
        avg,
        runs,
    )
    return True
