"""Pipeline: scraper -> filter -> db -> notifier."""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from job_watcher.config import Config, Profile
from job_watcher.db import JobDatabase
from job_watcher.filters import filter_offers
from job_watcher.models import JobOffer
from job_watcher.notifier import TelegramError, TelegramNotifier
from job_watcher.scrapers.base import run_multi_estado
from job_watcher.scrapers.registry import get_scraper


@dataclass
class RunStats:
    """Resumen de una ejecucion del pipeline."""

    scraped: int = 0
    new: int = 0
    matched: int = 0
    notified: int = 0
    errors: list[str] = field(default_factory=list)


def format_offer(offer: JobOffer) -> str:
    """Mensaje HTML para Telegram de una oferta."""
    lines = [f"<b>{offer.title}</b>"]
    if offer.company:
        lines.append(f"Empresa: {offer.company}")
    if offer.location:
        lines.append(f"Ubicacion: {offer.location}")
    if offer.published_at:
        date_str = offer.published_at.strftime("%d/%m/%Y")
        lines.append(f"Fecha: {date_str}")
    url = offer.url
    lines.append(f'<a href="{url}">Ver oferta</a>')
    return "\n".join(lines)


def format_summary(stats: RunStats) -> str:
    """Mensaje de resumen de una corrida."""
    if stats.notified == 0:
        return ""
    return (
        f"{stats.notified} oferta(s) nueva(s)\n"
        f"Revisadas: {stats.scraped} | Nuevas: {stats.new} | "
        f"Coinciden: {stats.matched}"
    )


def run_pipeline(config: Config) -> RunStats:
    """Ejecuta el flujo completo. Errores por portal no abortan el resto."""
    stats = RunStats()
    db = JobDatabase(config.database.path)
    notifier = TelegramNotifier(
        bot_token=config.telegram.bot_token,
        chat_id=config.telegram.chat_id,
        parse_mode=config.telegram.parse_mode,
        disable_web_page_preview=config.telegram.disable_web_page_preview,
    )

    for profile in config.profiles:
        if not profile.enabled:
            continue
        _run_for_profile(profile, config, db, notifier, stats)

    return stats


def _run_for_profile(
    profile: Profile,
    config: Config,
    db: JobDatabase,
    notifier: TelegramNotifier,
    stats: RunStats,
) -> None:
    for portal_name, enabled in profile.portals.items():
        if not enabled:
            continue
        try:
            scraper_cls = get_scraper(portal_name)
        except KeyError as exc:
            stats.errors.append(f"{portal_name}: {exc}")
            logger.error("Scraper no disponible: {}", exc)
            continue

        scraper = scraper_cls(
            timeout_seconds=config.scraping.timeout_seconds,
            user_agent=config.scraping.user_agent,
        )

        try:
            offers = run_multi_estado(
                scraper,
                config.scraping.estados,
                on_error=stats.errors.append,
            )
        except Exception as exc:
            stats.errors.append(f"{portal_name}: {exc!r}")
            logger.exception("[{}] fallo al scrapear", portal_name)
            continue

        stats.scraped += len(offers)
        matched = filter_offers(offers, profile)
        stats.matched += len(matched)

        for offer in matched:
            if not db.is_new(offer):
                continue
            stats.new += 1
            db.save(offer)
            try:
                notifier.send(format_offer(offer))
            except TelegramError as exc:
                stats.errors.append(f"telegram: {exc}")
                logger.exception("Fallo al notificar oferta {}", offer.external_id)
                continue
            db.mark_notified(offer)
            stats.notified += 1

        logger.info(
            "[{}] perfil={} scrapeadas={} notificadas={}",
            portal_name,
            profile.name,
            len(offers),
            stats.notified,
        )
