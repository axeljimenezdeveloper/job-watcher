"""Scraper de Mipleo Venezuela (www.mipleo.com.ve)."""

from __future__ import annotations

import random
import re
import time
from datetime import datetime
from typing import ClassVar

import requests
from bs4 import BeautifulSoup, Tag
from loguru import logger

from job_watcher.models import JobOffer
from job_watcher.scrapers.base import BaseScraper


class MipleoScraper(BaseScraper):
    """Extrae ofertas de www.mipleo.com.ve filtrando por estado."""

    portal = "mipleo"
    BASE_URL = "https://www.mipleo.com.ve/ofertas-de-trabajo/"
    ESTADOS: ClassVar[dict[str, str]] = {
        "nueva-esparta": "empleos-nueva-esparta",
        "distrito-capital": "empleos-distrito-capital",
        "miranda": "empleos-miranda",
        "carabobo": "empleos-carabobo",
        "zulia": "empleos-zulia",
    }
    PAGE_SIZE = 20

    def __init__(
        self,
        estado: str = "nueva-esparta",
        max_pages: int = 5,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        if estado not in self.ESTADOS:
            raise ValueError(f"estado no soportado: {estado}")
        self._estado = estado
        self._max_pages = max_pages

    def parse(self, html: str) -> list[JobOffer]:
        """Parsea UNA pagina. Filtra solo article.job-card (excluye ads)."""
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("article.job-card")
        if not cards:
            logger.warning("[{}] no se encontraron <article.job-card>", self.portal)
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
        anchor = card.select_one('a.stretched-link[href*="/oferta-de-trabajo-"]')
        if anchor is None:
            return None
        href = str(anchor.get("href", "")).split("?")[0]
        if not href:
            return None

        external_id = self._extract_id(href)
        if not external_id:
            return None

        title = str(anchor.get_text(" ", strip=True))
        if not title:
            return None

        company = self._extract_company(card)
        location = self._extract_location(card)
        published_at = self._extract_published(card)
        raw_text = self._extract_snippet(card)

        return JobOffer(
            portal=self.portal,
            title=title,
            company=company,
            location=location,
            url=href,
            external_id=external_id,
            published_at=published_at,
            raw_text=raw_text,
        )

    @staticmethod
    def _extract_id(url: str) -> str:
        """Extrae el ID numerico de "...-312273.html"."""
        match = re.search(r"-(\d+)\.html$", url)
        return match.group(1) if match else ""

    @staticmethod
    def _extract_company(card: Tag) -> str:
        """Texto tras <i class="bi bi-building">. "CONFIDENCIAL" se normaliza a ""."""
        div = card.select_one("div.job-header-main-left > div.small.text-secondary")
        if div is None:
            return ""
        text = str(div.get_text(" ", strip=True))
        if text.upper() == "CONFIDENCIAL":
            return ""
        return text

    @classmethod
    def _extract_location(cls, card: Tag) -> str:
        """Busca el span con hijo <i class="bi bi-geo-alt"> (sin :has())."""
        return cls._find_span_with_icon(card, "bi-geo-alt")

    @staticmethod
    def _extract_snippet(card: Tag) -> str:
        p = card.select_one("p.mb-2.small.text-body")
        if p is None:
            return ""
        return str(p.get_text(" ", strip=True))

    @classmethod
    def _extract_published(cls, card: Tag) -> datetime | None:
        """Lee el atributo datetime ISO 8601 de <time>."""
        time_el = card.select_one("div.time-publish > time")
        if time_el is None:
            return None
        iso = time_el.get("datetime")
        if not iso:
            return None
        try:
            return datetime.fromisoformat(str(iso))
        except ValueError:
            return None

    @staticmethod
    def _find_span_with_icon(card: Tag, icon_class: str) -> str:
        """Itera <span> buscando un hijo <i> con la clase dada (sin :has())."""
        for span in card.select(".job-body span"):
            icon = span.select_one("i")
            if icon is None:
                continue
            classes: set[str] = set(icon.get("class") or [])
            if icon_class in classes:
                return str(span.get_text(" ", strip=True))
        return ""

    @staticmethod
    def _extract_total(soup: BeautifulSoup) -> int:
        """Lee el contador "N Ofertas de trabajo" del <h2>."""
        h2 = soup.select_one("h2.h6.text-secondary")
        if h2 is None:
            return 20
        match = re.search(r"(\d+)", h2.get_text(" ", strip=True))
        if not match:
            return 20
        try:
            return int(match.group(1))
        except ValueError:
            return 20

    @staticmethod
    def _extract_slug(url: str) -> str:
        """De ".../empleos-nueva-esparta?pag=2" extrae "nueva-esparta"."""
        cleaned = url.split("?")[0].rstrip("/")
        match = re.search(r"empleos-([a-z-]+)$", cleaned)
        return match.group(1) if match else ""

    def _fetch_with_retry(self, url: str, tries: int = 3) -> str:
        last_exc: requests.RequestException | None = None
        for attempt in range(tries):
            try:
                return self.fetch(url)
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < tries - 1:
                    wait = 2**attempt + random.random()
                    logger.warning(
                        "Reintento {}/{} en {}: {}",
                        attempt + 1,
                        tries,
                        url,
                        exc,
                    )
                    time.sleep(wait)
        assert last_exc is not None
        raise last_exc

    def _with_pagination(self, slug: str, page: int) -> str:
        """Construye la URL paginada con ?pag=N&ord=da (orden estable)."""
        return f"{self.BASE_URL}empleos-{slug}?pag={page}&ord=da"

    def run(self, url: str) -> list[JobOffer]:
        """Override: pagina por estado con limite max_pages."""
        first_html = self._fetch_with_retry(url)
        first_soup = BeautifulSoup(first_html, "lxml")
        total = self._extract_total(first_soup)
        pages = min(self._max_pages, max(1, -(-total // self.PAGE_SIZE)))
        logger.info(
            "[{}] total estimado {} ofertas en {} paginas",
            self.portal,
            total,
            pages,
        )

        slug = self._extract_slug(url) or self.ESTADOS[self._estado].removeprefix("empleos-")

        seen: set[str] = set()
        all_offers: list[JobOffer] = []
        current_html = first_html

        for page in range(1, pages + 1):
            if page > 1:
                time.sleep(random.uniform(1.5, 3.0))
                page_url = self._with_pagination(slug, page)
                current_html = self._fetch_with_retry(page_url)
            for offer in self.parse(current_html):
                if offer.external_id not in seen:
                    seen.add(offer.external_id)
                    all_offers.append(offer)
            logger.debug(
                "[{}] pagina {}/{} -> {} acumuladas",
                self.portal,
                page,
                pages,
                len(all_offers),
            )

        logger.info("[{}] total recolectadas {}", self.portal, len(all_offers))
        return all_offers
