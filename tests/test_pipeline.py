"""Tests del pipeline end-to-end (con mocks)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from job_watcher import pipeline as p
from job_watcher.config import (
    AppConfig,
    Config,
    DatabaseConfig,
    Profile,
    ScrapingConfig,
    TelegramConfig,
)
from job_watcher.models import JobOffer


def _config(tmp_path: Path) -> Config:
    return Config(
        app=AppConfig(timezone="America/Caracas", log_level="INFO"),
        telegram=TelegramConfig(bot_token="123:abc", chat_id="42"),
        database=DatabaseConfig(path=tmp_path / "jobs.db"),
        scraping=ScrapingConfig(),
        profiles=[
            Profile(
                name="p",
                enabled=True,
                must_match_any=["inventario"],
                must_not_match=[],
                locations_any=[],
                portals={"unmejorempleo": True},
            )
        ],
    )


def _config_two_profiles(tmp_path: Path) -> Config:
    return Config(
        app=AppConfig(timezone="America/Caracas", log_level="INFO"),
        telegram=TelegramConfig(bot_token="123:abc", chat_id="42"),
        database=DatabaseConfig(path=tmp_path / "jobs.db"),
        scraping=ScrapingConfig(),
        profiles=[
            Profile(
                name="p1",
                enabled=True,
                must_match_any=["inventario"],
                must_not_match=[],
                locations_any=[],
                portals={"unmejorempleo": True},
            ),
            Profile(
                name="p2",
                enabled=True,
                must_match_any=["logistica"],
                must_not_match=[],
                locations_any=[],
                portals={"unmejorempleo": True},
            ),
        ],
    )


def _offer(ext_id: str = "1", title: str = "Analista de Inventarios") -> JobOffer:
    return JobOffer(
        portal="unmejorempleo",
        title=title,
        company="",
        location="Porlamar",
        url=f"https://x/{ext_id}",
        external_id=ext_id,
        published_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


def _setup_mocks(
    monkeypatch: pytest.MonkeyPatch, offers: list[JobOffer]
) -> tuple[MagicMock, MagicMock]:
    fake_scraper_instance = MagicMock()
    fake_scraper_instance.portal = "unmejorempleo"
    fake_scraper_instance.ESTADOS = {"nueva-esparta": "foo"}
    fake_scraper_instance.BASE_URL = "https://x/"
    fake_scraper_instance.run.return_value = offers
    fake_scraper_cls = MagicMock(return_value=fake_scraper_instance)
    monkeypatch.setattr(p, "get_scraper", MagicMock(return_value=fake_scraper_cls))

    fake_notifier = MagicMock()
    monkeypatch.setattr(p, "TelegramNotifier", MagicMock(return_value=fake_notifier))
    return fake_scraper_cls, fake_notifier


def test_pipeline_notifies_new_matched_offers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    _setup_mocks(monkeypatch, [_offer("1"), _offer("2", title="Camarera")])

    stats = p.run_pipeline(config)

    assert stats.scraped == 2
    assert stats.matched == 1
    assert stats.new == 1
    assert stats.notified == 1
    assert stats.errors == []


def test_pipeline_skips_already_known(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    _setup_mocks(monkeypatch, [_offer("1")])

    p.run_pipeline(config)
    stats2 = p.run_pipeline(config)

    assert stats2.scraped == 1
    assert stats2.matched == 1
    assert stats2.new == 0
    assert stats2.notified == 0


def test_pipeline_handles_scraper_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    fake_scraper_cls, _ = _setup_mocks(monkeypatch, [])
    fake_scraper_cls.return_value.run.side_effect = RuntimeError("boom")

    stats = p.run_pipeline(config)

    assert stats.scraped == 0
    assert stats.notified == 0
    assert any("boom" in e for e in stats.errors)


def test_pipeline_scrapes_each_portal_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Con 2 perfiles, el scraper debe instanciarse UNA sola vez por portal."""
    config = _config_two_profiles(tmp_path)
    fake_scraper_cls, _ = _setup_mocks(monkeypatch, [_offer("1")])

    p.run_pipeline(config)

    # Aunque hay 2 perfiles activos sobre unmejorempleo,
    # el scraper solo se instancia una vez (cache).
    assert fake_scraper_cls.call_count == 1


def test_pipeline_sends_daily_summary_if_no_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    _, fake_notifier = _setup_mocks(monkeypatch, [_offer("1", title="Camarera")])

    stats = p.run_pipeline(config)

    assert stats.notified == 0
    assert fake_notifier.send.call_count == 1
    text = fake_notifier.send.call_args[0][0]
    assert "Sin ofertas nuevas" in text


def test_pipeline_no_daily_summary_if_recently_sent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    _, fake_notifier = _setup_mocks(monkeypatch, [_offer("1", title="Camarera")])

    p.run_pipeline(config)
    assert fake_notifier.send.call_count == 1

    p.run_pipeline(config)
    assert fake_notifier.send.call_count == 1


def test_pipeline_no_summary_when_notified(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    _, fake_notifier = _setup_mocks(monkeypatch, [_offer("1")])

    stats = p.run_pipeline(config)

    assert stats.notified == 1
    assert fake_notifier.send.call_count == 1
    text = fake_notifier.send.call_args[0][0]
    assert "Sin ofertas nuevas" not in text


def test_format_offer_includes_profile_emoji() -> None:
    offer = _offer("1", title="Frontend Developer Sr")
    text = p.format_offer(offer, "Frontend Developer (React/TS/RN)")
    assert "💻" in text
    assert offer.title in text


def test_format_offer_includes_remote_badge() -> None:
    offer = _offer("1", title="Dev remoto")
    text = p.format_offer(offer, "QA Engineer / Tester")
    assert "🏠 Remoto" in text


def test_pipeline_skips_cross_portal_duplicate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Dos portales publican la misma oferta: solo una se notifica.

    Requiere company no vacia (el dedup cross-portal no aplica sin empresa).
    """
    config = _config(tmp_path)

    # Ambas ofertas comparten title + company para que el dedup aplique.
    dup_offer = JobOffer(
        portal="unmejorempleo",
        title="Analista de Inventarios",
        company="ACME Corp",
        location="Porlamar",
        url="https://x/unmejorempleo",
        external_id="1",
        published_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    dup_offer_other = JobOffer(
        portal="computrabajo",
        title="Analista de Inventarios",
        company="ACME Corp",
        location="Mariño",
        url="https://x/computrabajo",
        external_id="999",
        published_at=datetime(2026, 11, 1, tzinfo=UTC),
    )

    fake_scraper_instance = MagicMock()
    fake_scraper_instance.portal = "unmejorempleo"
    fake_scraper_instance.ESTADOS = {"nueva-esparta": "foo"}
    fake_scraper_instance.BASE_URL = "https://x/"
    fake_scraper_instance.run.return_value = [dup_offer, dup_offer_other]
    fake_scraper_cls = MagicMock(return_value=fake_scraper_instance)
    monkeypatch.setattr(p, "get_scraper", MagicMock(return_value=fake_scraper_cls))

    fake_notifier = MagicMock()
    monkeypatch.setattr(p, "TelegramNotifier", MagicMock(return_value=fake_notifier))

    stats = p.run_pipeline(config)

    # Solo 1 notificada (la primera), la segunda se dedupea
    assert stats.notified == 1
    assert fake_notifier.send.call_count == 1
