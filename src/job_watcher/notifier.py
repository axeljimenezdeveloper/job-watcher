"""Notificador de Telegram via API HTTPS."""

from __future__ import annotations

from typing import Any

import requests
from loguru import logger


class TelegramError(RuntimeError):
    """Error al enviar un mensaje a Telegram."""


class TelegramNotifier:
    """Envia mensajes a un chat de Telegram usando la API Bot."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
        timeout_seconds: int = 15,
    ) -> None:
        self._chat_id = chat_id
        self._parse_mode = parse_mode
        self._disable_web_page_preview = disable_web_page_preview
        self._timeout = timeout_seconds
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    def send(self, text: str) -> dict[str, Any]:
        """Envia text al chat configurado. Retorna la respuesta de la API."""
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": self._parse_mode,
            "disable_web_page_preview": self._disable_web_page_preview,
        }
        try:
            response = requests.post(
                f"{self._base_url}/sendMessage",
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Fallo al enviar mensaje a Telegram: {}", exc)
            raise TelegramError(str(exc)) from exc

        logger.debug("Mensaje enviado a chat {}", self._chat_id)
        result: dict[str, Any] = response.json()
        return result
