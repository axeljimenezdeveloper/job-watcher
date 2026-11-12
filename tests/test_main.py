"""Tests del entrypoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from job_watcher import __main__ as entry
from job_watcher.config import (
    AppConfig,
    Config,
    DatabaseConfig,
    Profile,
    ScrapingConfig,
    TelegramConfig,
)
from job_watcher.pipeline import RunStats


def _fake_config() -> Config:
    return Config(
        app=AppConfig(timezone="America/Caracas", log_level="INFO"),
        telegram=TelegramConfig(bot_token="123:abc", chat_id="42"),
        database=DatabaseConfig(path=Path("/tmp/x.db")),
        scraping=ScrapingConfig(),
        profiles=[Profile(name="p", enabled=True)],
    )


def test_main_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entry, "load_config", lambda: _fake_config())

    mock_stats = RunStats(scraped=3, new=1, matched=1, notified=1)
    monkeypatch.setattr(entry, "run_pipeline", MagicMock(return_value=mock_stats))

    rc = entry.main()

    assert rc == 0


def test_main_with_errors_still_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entry, "load_config", lambda: _fake_config())

    mock_stats = RunStats(errors=["unmejorempleo: timeout"])
    monkeypatch.setattr(entry, "run_pipeline", MagicMock(return_value=mock_stats))

    rc = entry.main()

    assert rc == 0
