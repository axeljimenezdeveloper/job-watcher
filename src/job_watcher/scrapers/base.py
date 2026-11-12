"""Interfaz base para todos los scrapers."""

from __future__ import annotations

from abc import ABC, abstractmethod

import requests
from loguru import logger

from job_watcher.models import JobOffer


class BaseScraper(ABC):
    """Contrato comun: un portal por clase, fetch + parse separados."""

    portal: str = ""

    def __init__(
        self,
        timeout_seconds: int = 30,
        user_agent: str = "",
    ) -> None:
        self._timeout = timeout_seconds
        self._user_agent = user_agent or "job-watcher/0.1"

    def fetch(self, url: str) -> str:
        """Descarga el HTML de url. Puede lanzar requests.RequestException."""
        logger.debug("[{}] fetching {}", self.portal, url)
        response = requests.get(
            url,
            timeout=self._timeout,
            headers={"User-Agent": self._user_agent},
        )
        response.raise_for_status()
        return response.text

    @abstractmethod
    def parse(self, html: str) -> list[JobOffer]:
        """Extrae ofertas del HTML. Debe estar implementado por subclases."""

    def run(self, url: str) -> list[JobOffer]:
        """Compone fetch + parse. Errores de red se propagan."""
        html = self.fetch(url)
        offers = self.parse(html)
        logger.info("[{}] parsed {} offers", self.portal, len(offers))
        return offers
