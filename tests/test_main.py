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
from job_watcher.notifier import TelegramError


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

    mock_notifier = MagicMock()
    mock_notifier.send.return_value = {"ok": True}
    monkeypatch.setattr(entry, "TelegramNotifier", MagicMock(return_value=mock_notifier))

    rc = entry.main()

    assert rc == 0
    assert mock_notifier.send.call_count == 1


def test_main_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entry, "load_config", lambda: _fake_config())

    mock_notifier = MagicMock()
    mock_notifier.send.side_effect = TelegramError("boom")
    monkeypatch.setattr(entry, "TelegramNotifier", MagicMock(return_value=mock_notifier))

    rc = entry.main()

    assert rc == 1
