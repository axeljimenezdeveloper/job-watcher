"""Scraper de Computrabajo Venezuela (ve.computrabajo.com)."""

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


class ComputrabajoScraper(BaseScraper):
    """Extrae ofertas de ve.computrabajo.com filtrando por estado."""

    portal = "computrabajo"
    BASE_URL = "https://ve.computrabajo.com/"
    ESTADOS: ClassVar[dict[str, str]] = {
        "nueva-esparta": "empleos-en-nueva-esparta",
        "distrito-capital": "empleos-en-distrito-capital",
        "miranda": "empleos-en-miranda",
        "carabobo": "empleos-en-carabobo",
        "zulia": "empleos-en-zulia",
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

    def fetch(self, url: str) -> str:
        """Override: Computrabajo sirve UTF-8 explicito. Force encoding."""
        logger.debug("[{}] fetching {}", self.portal, url)
        response = requests.get(
            url,
            timeout=self._timeout,
            headers={"User-Agent": self._user_agent},
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text

    def parse(self, html: str) -> list[JobOffer]:
        """Parsea UNA pagina de resultados. Ignora slots de AdSense."""
        soup = BeautifulSoup(html, "lxml")
        articles = soup.select("article.box_offer")
        if not articles:
            logger.warning("[{}] no se encontraron <article.box_offer>", self.portal)
            return []

        offers: list[JobOffer] = []
        for article in articles:
            if not isinstance(article, Tag):
                continue
            offer = self._parse_card(article)
            if offer is not None:
                offers.append(offer)
        return offers

    def _parse_card(self, article: Tag) -> JobOffer | None:
        external_id = str(article.get("data-id", "")).strip()
        if not external_id:
            return None

        anchor = article.select_one("h2 > a.js-o-link[href]")
        if anchor is None:
            return None
        title = anchor.get_text(" ", strip=True)
        if not title:
            return None

        href = str(anchor.get("href", "")).split("#")[0]
        url = urljoin(self.BASE_URL, href) if href else ""
        if not url:
            return None

        company = ""
        company_anchor = article.select_one("p.dFlex a[offer-grid-article-company-url]")
        if company_anchor is not None:
            company = str(company_anchor.get_text(" ", strip=True))

        location = ""
        loc_span = article.select_one("p.fs16 > span.mr10")
        if loc_span is not None:
            location = str(loc_span.get_text(" ", strip=True))

        published_at = None
        date_el = article.select_one("p.fs13.fc_aux")
        if date_el is not None:
            published_at = self._parse_relative_date(date_el.get_text(" ", strip=True))

        return JobOffer(
            portal=self.portal,
            title=title,
            company=company,
            location=location,
            url=url,
            external_id=external_id,
            published_at=published_at,
            raw_text="",  # no hay snippet en el listado
        )

    @staticmethod
    def _parse_relative_date(text: str) -> datetime | None:
        """Convierte "Ahora", "Ayer", "Hace N <unidad>" a datetime UTC."""
        normalized = " ".join(text.lower().split())
        if not normalized:
            return None
        now = datetime.now(UTC)
        if normalized == "ahora":
            return now
        if normalized == "ayer":
            return now - timedelta(days=1)
        match = re.search(
            r"hace\s+(\d+)\s+(minuto|hora|d[ií]a|semana|mes|a[nñ]o)s?",
            normalized,
        )
        if not match:
            return None
        amount = int(match.group(1))
        unit = match.group(2)
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
        """Extrae el total del <h1.title_page>. Default 20 si no encuentra."""
        h1_span = soup.select_one("h1.title_page > span.fwB")
        if h1_span is None:
            return 20
        try:
            return int(h1_span.get_text(strip=True))
        except ValueError:
            return 20

    @staticmethod
    def _with_pagination(base_url: str, page: int) -> str:
        """Construye ?p=N preservando query. page es 1-based."""
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        query["p"] = [str(page)]
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
