"""Tests del notificador de Telegram."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from job_watcher.notifier import TelegramError, TelegramNotifier


def test_send_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 42}}
    mock_response.raise_for_status.return_value = None

    mock_post = MagicMock(return_value=mock_response)
    monkeypatch.setattr("job_watcher.notifier.requests.post", mock_post)

    notifier = TelegramNotifier(bot_token="123:abc", chat_id="42")
    result = notifier.send("hola")

    assert result["ok"] is True
    assert mock_post.call_count == 1
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.telegram.org/bot123:abc/sendMessage"
    assert kwargs["json"]["chat_id"] == "42"
    assert kwargs["json"]["text"] == "hola"
    assert kwargs["json"]["parse_mode"] == "HTML"


def test_send_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
    monkeypatch.setattr(
        "job_watcher.notifier.requests.post",
        MagicMock(return_value=mock_response),
    )

    notifier = TelegramNotifier(bot_token="123:abc", chat_id="42")

    with pytest.raises(TelegramError):
        notifier.send("hola")
