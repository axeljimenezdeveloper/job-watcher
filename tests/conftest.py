"""Fixtures compartidas de pytest."""

from __future__ import annotations

import pytest


@pytest.fixture()
def fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "99999")
