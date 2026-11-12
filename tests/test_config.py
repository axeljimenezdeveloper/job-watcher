"""Tests del cargador de configuracion."""

from __future__ import annotations

from pathlib import Path

import pytest

from job_watcher.config import load_config


def _empty_env(tmp_path: Path) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    return env_file


def test_load_config_ok(fake_env: None, tmp_path: Path) -> None:
    cfg = load_config(env_file=_empty_env(tmp_path))

    assert cfg.telegram.bot_token == "123:fake-token"
    assert cfg.telegram.chat_id == "99999"
    assert cfg.app.timezone == "America/Caracas"
    assert cfg.app.log_level == "INFO"
    assert len(cfg.profiles) >= 1
    assert cfg.profiles[0].name
    assert cfg.profiles[0].enabled is True


def test_load_config_missing_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "99999")

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        load_config(env_file=_empty_env(tmp_path))
