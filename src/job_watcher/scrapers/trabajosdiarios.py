"""Scraper de Trabajos Diarios Venezuela (ve.trabajosdiarios.com)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import ClassVar
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from loguru import logger

from job_watcher.models import JobOffer
from job_watcher.scrapers.base import BaseScraper


class TrabajosDiariosScraper(BaseScraper):
    """Extrae ofertas de ve.trabajosdiarios.com filtrando por estado."""

    portal = "trabajosdiarios"
    BASE_URL = "https://ve.trabajosdiarios.com/"
    ESTADOS: ClassVar[dict[str, str]] = {
        "nueva-esparta": "ofertas-trabajo/en-nueva-esparta",
        "distrito-capital": "ofertas-trabajo/en-distrito-capital",
        "miranda": "ofertas-trabajo/en-miranda",
        "carabobo": "ofertas-trabajo/en-carabobo",
        "zulia": "ofertas-trabajo/en-zulia",
    }

    def __init__(self, estado: str = "nueva-esparta", **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        if estado not in self.ESTADOS:
            raise ValueError(f"estado no soportado: {estado}")
        self._estado = estado

    def parse(self, html: str) -> list[JobOffer]:
        """Parsea la pagina. Excluye chip de filtro y ads (no son div.card)."""
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("div.list-group.list-group-flush > div.card")
        if not cards:
            logger.warning("[{}] no se encontraron <div.card>", self.portal)
            return []

        offers: list[JobOffer] = []
        for card in cards:
            if not isinstance(card, Tag):
                continue
            offer = self._parse_card(card)
            if offer is not None:
                offers.append(offer)
        return offers

    def _parse_card(self, card: Tag) -> JobOffer | None:
        anchor = card.select_one("a[data-enlace-oferta='1'][href]")
        if anchor is None:
            return None
        href = str(anchor.get("href", "")).split("#")[0]
        url = urljoin(self.BASE_URL, href) if href else ""
        if not url:
            return None

        external_id = self._extract_id(card, url)
        if not external_id:
            return None

        title_el = card.select_one("h3.font_2")
        if title_el is None:
            return None
        title = str(title_el.get_text(" ", strip=True))
        if not title:
            return None

        company = ""
        company_el = card.select_one("p.text-secondary.opacity-75.small")
        if company_el is not None:
            company = str(company_el.get_text(" ", strip=True))

        location = ""
        published_at = None
        spans = card.select("span.text-dark")
        if len(spans) >= 1:
            location = str(spans[0].get_text(" ", strip=True))
        if len(spans) >= 2:
            published_at = self._parse_date(spans[1].get_text(" ", strip=True))

        snippet_el = card.select_one("div.py-2.py-xl-1 > p")
        raw_text = snippet_el.get_text(" ", strip=True) if snippet_el else ""

        return JobOffer(
            portal=self.portal,
            title=title,
            company=company,
            location=location,
            url=url,
            external_id=external_id,
            published_at=published_at,
            raw_text=str(raw_text),
        )

    @staticmethod
    def _extract_id(card: Tag, url: str) -> str:
        """Intenta data-oferta-id del boton, fallback a regex sobre la URL."""
        btn = card.select_one("button.btn-favorito[data-oferta-id]")
        if btn is not None:
            ext = str(btn.get("data-oferta-id", "")).strip()
            if ext:
                return ext
        match = re.search(r"/trabajo/(\d+)/", url)
        return match.group(1) if match else ""

    @staticmethod
    def _parse_date(text: str) -> datetime | None:
        """Convierte DD/MM/YYYY a datetime UTC."""
        match = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
        if not match:
            return None
        try:
            return datetime(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1)),
                tzinfo=UTC,
            )
        except ValueError:
            return None

    def run(self, url: str) -> list[JobOffer]:
        """Override: sin paginacion. Un solo GET por estado."""
        base_url = url or urljoin(self.BASE_URL, self.ESTADOS[self._estado])
        html = self.fetch(base_url)
        offers = self.parse(html)
        logger.info("[{}] total recolectadas {}", self.portal, len(offers))
        return offers
