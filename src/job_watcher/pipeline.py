"""Pipeline: scraper -> filter -> db -> notifier."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from loguru import logger

from job_watcher.config import Config, Profile
from job_watcher.db import JobDatabase
from job_watcher.filters import filter_offers
from job_watcher.models import JobOffer
from job_watcher.monitor import check_and_alert
from job_watcher.notifier import TelegramError, TelegramNotifier
from job_watcher.scrapers.base import run_multi_estado
from job_watcher.scrapers.registry import get_scraper

MAX_WORKERS = 6
DAILY_SUMMARY_THRESHOLD_HOURS = 20

_EMOJI_BY_PROFILE = {
    "Frontend Developer": "💻",
    "QA Engineer": "🧪",
    "Soporte Tecnico": "🔧",
    "Asistente Tecnico": "📋",
}
_REMOTE_KEYWORDS = ("remoto", "remote", "home office", "teletrabajo")


@dataclass
class RunStats:
    """Resumen de una ejecucion del pipeline."""

    scraped: int = 0
    new: int = 0
    matched: int = 0
    notified: int = 0
    errors: list[str] = field(default_factory=list)


def _emoji_for_profile(profile_name: str) -> str:
    """Emoji segun el nombre del perfil."""
    for prefix, emoji in _EMOJI_BY_PROFILE.items():
        if profile_name.startswith(prefix):
            return emoji
    return "📌"


def _is_remote(offer: JobOffer) -> bool:
    """True si la oferta menciona trabajo remoto."""
    haystack = f"{offer.title} {offer.raw_text} {offer.location}".lower()
    return any(kw in haystack for kw in _REMOTE_KEYWORDS)


def format_offer(offer: JobOffer, profile_name: str = "") -> str:
    """Mensaje HTML para Telegram de una oferta, con emoji por perfil."""
    lines = [f"{_emoji_for_profile(profile_name)} <b>{offer.title}</b>"]
    if offer.company:
        lines.append(f"🏢 {offer.company}")
    if _is_remote(offer):
        lines.append("🏠 Remoto")
    elif offer.location:
        lines.append(f"📍 {offer.location}")
    if offer.published_at:
        lines.append(f"📅 {offer.published_at.strftime('%d/%m/%Y')}")
    if offer.raw_text:
        snippet = offer.raw_text[:200].rstrip()
        if len(offer.raw_text) > 200:
            snippet += "…"
        lines.append("")
        lines.append(snippet)
    lines.append("")
    lines.append(f'🔗 <a href="{offer.url}">Ver oferta</a>')
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
    """Scrapea cada portal UNA vez (en paralelo), luego aplica cada perfil."""
    stats = RunStats()
    db = JobDatabase(config.database.path)
    notifier = TelegramNotifier(
        bot_token=config.telegram.bot_token,
        chat_id=config.telegram.chat_id,
        parse_mode=config.telegram.parse_mode,
        disable_web_page_preview=config.telegram.disable_web_page_preview,
    )

    active_portals = _collect_active_portals(config.profiles)
    logger.info("Portales activos: {}", sorted(active_portals))

    offers_by_portal = _scrape_all_portals(active_portals, config, stats)
    _monitor_portals(offers_by_portal, db, notifier)

    for profile in config.profiles:
        if not profile.enabled:
            continue
        _apply_profile(profile, offers_by_portal, db, notifier, stats)

    if stats.notified == 0:
        _maybe_send_daily_summary(db, notifier, stats)

    return stats


def _collect_active_portals(profiles: list[Profile]) -> set[str]:
    """Union de portales activos sobre todos los perfiles habilitados."""
    portals: set[str] = set()
    for profile in profiles:
        if not profile.enabled:
            continue
        for name, enabled in profile.portals.items():
            if enabled:
                portals.add(name)
    return portals


def _scrape_one_portal(portal_name: str, config: Config) -> tuple[str, list[JobOffer], list[str]]:
    """Scrapea un solo portal. Retorna (name, offers, errors locales)."""
    errors: list[str] = []
    try:
        scraper_cls = get_scraper(portal_name)
    except KeyError as exc:
        errors.append(f"{portal_name}: {exc}")
        return (portal_name, [], errors)

    scraper = scraper_cls(
        timeout_seconds=config.scraping.timeout_seconds,
        user_agent=config.scraping.user_agent,
    )

    try:
        offers = run_multi_estado(
            scraper,
            config.scraping.estados,
            on_error=errors.append,
        )
    except Exception as exc:
        errors.append(f"{portal_name}: {exc!r}")
        logger.exception("[{}] fallo al scrapear", portal_name)
        return (portal_name, [], errors)

    return (portal_name, offers, errors)


def _scrape_all_portals(
    portals: set[str],
    config: Config,
    stats: RunStats,
) -> dict[str, list[JobOffer]]:
    """Scrapea todos los portales en paralelo (max MAX_WORKERS simultaneos)."""
    result: dict[str, list[JobOffer]] = {}
    sorted_portals = sorted(portals)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_scrape_one_portal, name, config): name for name in sorted_portals
        }
        for future in as_completed(futures):
            portal_name, offers, errors = future.result()
            for err in errors:
                stats.errors.append(err)
                logger.error("Error scraping: {}", err)
            result[portal_name] = offers
            stats.scraped += len(offers)
            logger.info("[{}] total scrapeado: {} ofertas", portal_name, len(offers))

    return result


def _monitor_portals(
    offers_by_portal: dict[str, list[JobOffer]],
    db: JobDatabase,
    notifier: TelegramNotifier,
) -> None:
    """Registra el conteo por portal y envia alertas si cae >50%."""
    for portal_name, offers in offers_by_portal.items():
        count = len(offers)
        check_and_alert(portal_name, count, db, notifier)
        db.log_scrape_run(portal_name, count)


def _apply_profile(
    profile: Profile,
    offers_by_portal: dict[str, list[JobOffer]],
    db: JobDatabase,
    notifier: TelegramNotifier,
    stats: RunStats,
) -> None:
    """Filtra el cache contra un perfil y notifica los matches nuevos."""
    for portal_name, offers in offers_by_portal.items():
        if not profile.portals.get(portal_name, False):
            continue

        matched = filter_offers(offers, profile)
        stats.matched += len(matched)

        notified_here = 0
        for offer in matched:
            if not db.is_new(offer):
                continue
            stats.new += 1
            db.save(offer)
            try:
                notifier.send(format_offer(offer, profile.name))
            except TelegramError as exc:
                stats.errors.append(f"telegram: {exc}")
                logger.exception("Fallo al notificar oferta {}", offer.external_id)
                continue
            db.mark_notified(offer)
            stats.notified += 1
            notified_here += 1

        logger.info(
            "[{}] perfil={} matched={} notificadas={}",
            portal_name,
            profile.name,
            len(matched),
            notified_here,
        )


def _maybe_send_daily_summary(
    db: JobDatabase,
    notifier: TelegramNotifier,
    stats: RunStats,
) -> None:
    """Envia un resumen si no hubo matches y no se envio en las ultimas 20h."""
    if db.was_summary_sent_since(DAILY_SUMMARY_THRESHOLD_HOURS):
        return
    text = (
        "📭 <b>Sin ofertas nuevas</b>\n"
        f"Revisadas: {stats.scraped}\n"
        f"Coincidencias de perfil: {stats.matched}\n"
        f"Errores: {len(stats.errors)}"
    )
    try:
        notifier.send(text)
    except TelegramError as exc:
        logger.error("No se pudo enviar resumen diario: {}", exc)
        return
    db.log_summary_sent()
    logger.info("Resumen diario enviado (sin matches)")
