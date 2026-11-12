"""Scraper de Trabajo.org Venezuela (ve.trabajo.org)."""

from __future__ import annotations

import random
import re
import time
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag
from loguru import logger

from job_watcher.models import JobOffer
from job_watcher.scrapers.base import BaseScraper


class TrabajoOrgScraper(BaseScraper):
    """Extrae ofertas de ve.trabajo.org filtrando por estado."""

    portal = "trabajo_org"
    BASE_URL = "https://ve.trabajo.org/"
    ESTADOS: ClassVar[dict[str, str]] = {
        "nueva-esparta": "empleo/Nueva+Esparta",
        "distrito-capital": "empleo/Distrito+Capital",
        "miranda": "empleo/Miranda",
        "carabobo": "empleo/Carabobo",
        "zulia": "empleo/Zulia",
    }

    def __init__(
        self,
        estado: str = "nueva-esparta",
        max_pages: int = 10,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        if estado not in self.ESTADOS:
            raise ValueError(f"estado no soportado: {estado}")
        self._estado = estado
        self._max_pages = max_pages

    def parse(self, html: str) -> list[JobOffer]:
        """Parsea el listado de UNA pagina. Excluye anuncios intercalados."""
        soup = BeautifulSoup(html, "lxml")
        items = soup.select("ul.nf-job-list > li.job-item")
        if not items:
            logger.warning("[{}] no se encontraron <li.job-item>", self.portal)
            return []

        offers: list[JobOffer] = []
        for li in items:
            if not isinstance(li, Tag):
                continue
            classes = set(li.get("class") or [])
            if "alert-capture-li" in classes:
                continue
            offer = self._parse_card(li)
            if offer is not None:
                offers.append(offer)
        return offers

    def _parse_card(self, li: Tag) -> JobOffer | None:
        external_id = str(li.get("data-id", "")).strip()
        if not external_id:
            return None

        anchor = li.select_one("h3 > a[href]")
        if anchor is None:
            return None
        title = anchor.get_text(" ", strip=True)
        if not title:
            return None

        href = str(anchor.get("href", "")).split("?")[0]
        url = urljoin(self.BASE_URL, href) if href else ""
        if not url:
            url = str(li.get("data-url", "")).split("?")[0]
        if not url:
            return None

        company = self._extract_field(li, "lnr-briefcase")
        location = self._extract_field(li, "lnr-map-marker")

        published_at = None
        date_el = li.select_one("p.text-muted small")
        if date_el is not None:
            published_at = self._parse_relative_date(date_el.get_text(" ", strip=True))

        snippet_el = li.select_one("div.nf-job-list-desc p.mb-0")
        raw_text = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if len(raw_text) > 300:
            raw_text = raw_text[:300].rstrip()

        return JobOffer(
            portal=self.portal,
            title=title,
            company=company,
            location=location,
            url=url,
            external_id=external_id,
            published_at=published_at,
            raw_text=raw_text,
        )

    @staticmethod
    def _extract_field(li: Tag, icon_class: str) -> str:
        """Extrae el texto de un <span> que contiene <i class="lnr-...">."""
        for span in li.select("div.nf-job-list-info span"):
            icon = span.select_one("i")
            if icon is None:
                continue
            classes = set(icon.get("class") or [])
            if icon_class in classes:
                return str(span.get_text(" ", strip=True))
        return ""

    @staticmethod
    def _parse_relative_date(text: str) -> datetime | None:
        """Convierte "Hace N <unidad>" a datetime UTC relativo a now()."""
        match = re.search(
            r"hace\s+(\d+)\s+(minuto|hora|d[ií]a|semana|mes|a[nñ]o)s?",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None
        amount = int(match.group(1))
        unit = match.group(2).lower()
        now = datetime.now(UTC)
        if unit.startswith("minuto"):
            return now - timedelta(minutes=amount)
        if unit.startswith("hora"):
            return now - timedelta(hours=amount)
        if unit.startswith("d"):
            return now - timedelta(days=amount)
        if unit.startswith("semana"):
            return now - timedelta(weeks=amount)
        if unit.startswith("mes"):
            return now - timedelta(days=amount * 30)
        if unit.startswith("a") or unit.startswith("ñ"):
            return now - timedelta(days=amount * 365)
        return None

    @staticmethod
    def _extract_total(soup: BeautifulSoup) -> int:
        """Extrae el total de ofertas del <title>. Ej: "... - 85 | ..." -> 85."""
        title = soup.find("title")
        if title is not None:
            match = re.search(r"-\s*(\d+)\s*\|", title.get_text())
            if match:
                return int(match.group(1))
        return 20

    @staticmethod
    def _with_pagination(base_url: str, page: int) -> str:
        """Construye ?page=N preservando query existente. page es 1-based."""
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        query["page"] = [str(page)]
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    def run(self, url: str) -> list[JobOffer]:
        """Override: pagina sobre el listado y dedupe por external_id."""
        base_url = url or urljoin(self.BASE_URL, self.ESTADOS[self._estado])

        first_html = self._fetch_with_retry(base_url)
        first_soup = BeautifulSoup(first_html, "lxml")
        total = self._extract_total(first_soup)
        pages = min(self._max_pages, max(1, -(-total // 20)))
        logger.info(
            "[{}] total estimado {} ofertas en {} paginas",
            self.portal,
            total,
            pages,
        )

        seen: set[str] = set()
        all_offers: list[JobOffer] = []

        for page in range(1, pages + 1):
            if page == 1:
                current_html = first_html
            else:
                time.sleep(random.uniform(1.5, 3.0))
                page_url = self._with_pagination(base_url, page)
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
