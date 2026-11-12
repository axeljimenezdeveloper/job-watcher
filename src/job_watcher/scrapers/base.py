"""Interfaz base para todos los scrapers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import ClassVar

import requests
from loguru import logger

from job_watcher.models import JobOffer


class BaseScraper(ABC):
    """Contrato comun: un portal por clase, fetch + parse separados."""

    portal: str = ""
    BASE_URL: ClassVar[str] = ""
    ESTADOS: ClassVar[dict[str, str]] = {}

    def __init__(
        self,
        timeout_seconds: int = 30,
        user_agent: str = "",
    ) -> None:
        self._timeout = timeout_seconds
        self._user_agent = user_agent or "job-watcher/0.1"
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self._user_agent})

    def fetch(self, url: str) -> str:
        """Descarga el HTML de url. Puede lanzar requests.RequestException."""
        logger.debug("[{}] fetching {}", self.portal, url)
        response = self._session.get(url, timeout=self._timeout)
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


def run_multi_estado(
    scraper: BaseScraper,
    estados: list[str],
    on_error: Callable[[str], None] | None = None,
) -> list[JobOffer]:
    """Ejecuta el scraper sobre varios estados, deduplicando por external_id."""
    all_offers: list[JobOffer] = []
    seen: set[str] = set()
    for estado in estados:
        if estado not in scraper.ESTADOS:
            logger.debug("[{}] estado no soportado: {}", scraper.portal, estado)
            continue
        url = scraper.BASE_URL + scraper.ESTADOS[estado]
        try:
            offers = scraper.run(url)
        except Exception as exc:
            msg = f"{scraper.portal} estado={estado}: {exc}"
            logger.warning("[{}] estado={} fallo: {}", scraper.portal, estado, exc)
            if on_error is not None:
                on_error(msg)
            continue
        logger.info("[{}] {} -> {} ofertas", scraper.portal, estado, len(offers))
        for offer in offers:
            if offer.external_id not in seen:
                seen.add(offer.external_id)
                all_offers.append(offer)
    return all_offers
