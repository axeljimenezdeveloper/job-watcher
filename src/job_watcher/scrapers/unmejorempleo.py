"""Scraper de UnMejorEmpleo (unmejorempleo.com.ve)."""

from __future__ import annotations

import random
import re
import time
from datetime import UTC, datetime
from typing import ClassVar
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag
from loguru import logger

from job_watcher.models import JobOffer
from job_watcher.scrapers.base import BaseScraper


class UnMejorEmpleoScraper(BaseScraper):
    """Extrae ofertas del portal unmejorempleo.com.ve."""

    portal = "unmejorempleo"
    BASE_URL = "https://www.unmejorempleo.com.ve/"
    ESTADOS: ClassVar[dict[str, str]] = {
        "nueva-esparta": "empleo-en-nueva-esparta.html",
        "distrito-capital": "empleo-en-distrito-capital.html",
        "miranda": "empleo-en-miranda.html",
        "carabobo": "empleo-en-carabobo.html",
        "zulia": "empleo-en-zulia.html",
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
        """Parsea el listado de UNA pagina. No maneja paginacion."""
        soup = BeautifulSoup(html, "lxml")
        article = soup.select_one("section.col-md-9 article")
        if article is None:
            logger.warning("[{}] no se encontro <article> en el HTML", self.portal)
            return []

        offers: list[JobOffer] = []
        for div in article.find_all("div", recursive=False):
            if not isinstance(div, Tag):
                continue
            classes = set(div.get("class") or [])
            if "advert" in classes:
                continue  # anuncios intercalados, sin <h3>
            if not ({"item-normal", "item-destacado"} & classes):
                continue
            offer = self._parse_card(div)
            if offer is not None:
                offers.append(offer)
        return offers

    def _parse_card(self, div: Tag) -> JobOffer | None:
        anchor = div.select_one("h3 a[href]")
        if anchor is None:
            return None
        href = str(anchor.get("href", ""))
        url = urljoin(self.BASE_URL, href.split("?")[0])
        if "/empleo-en_" not in url:
            return None

        external_id = self._extract_id(url)
        if not external_id:
            return None

        title = anchor.get_text(" ", strip=True)
        if not title:
            return None

        location_raw = ""
        snippet = ""
        meta_raw = ""
        for li in div.select("ul.list-unstyled > li"):
            classes = set(li.get("class") or [])
            text = li.get_text(" ", strip=True)
            if "text-primary" in classes:
                location_raw = text
            elif "text-warning" in classes:
                meta_raw = text
            elif text and not snippet:
                snippet = text

        city, state = self._split_location(location_raw)
        location = f"{city}, {state}" if city and state else (city or state)
        published_at = self._extract_date(meta_raw)

        return JobOffer(
            portal=self.portal,
            title=title,
            company="",  # no viene en el listado
            location=location,
            url=url,
            external_id=external_id,
            published_at=published_at,
            raw_text=snippet,
        )

    @staticmethod
    def _split_location(text: str) -> tuple[str, str]:
        """De "Ubicacion: X | Estado : Y" extrae (X, Y) sin importar tildes."""
        clean = re.sub(r"Ubicaci[oó]n\s*:\s*", "", text, flags=re.IGNORECASE)
        if "|" not in clean:
            return clean.strip(), ""
        city_raw, _, state_raw = clean.partition("|")
        state = re.sub(r"Estado\s*:\s*", "", state_raw, flags=re.IGNORECASE).strip()
        return city_raw.strip(), state

    @staticmethod
    def _extract_date(text: str) -> datetime | None:
        """De "Publicacion: dd/mm/yyyy - ..." extrae datetime UTC."""
        match = re.search(r"(\d{2}/\d{2}/\d{4})", text)
        if not match:
            return None
        try:
            naive = datetime.strptime(match.group(1), "%d/%m/%Y")
        except ValueError:
            return None
        return naive.replace(tzinfo=UTC)

    @staticmethod
    def _extract_id(url: str) -> str:
        """De "...-5914683.html" extrae "5914683"."""
        match = re.search(r"-(\d+)\.html", url)
        return match.group(1) if match else ""

    def run(self, url: str) -> list[JobOffer]:
        """Override: pagina sobre el listado y dedupe por external_id."""
        base_url = url or urljoin(self.BASE_URL, self.ESTADOS[self._estado])

        first_html = self._fetch_with_retry(base_url)
        first_soup = BeautifulSoup(first_html, "lxml")
        total = self._extract_total(first_soup)
        pages = min(self._max_pages, max(1, -(-total // 20)))  # ceil division
        logger.info(
            "[{}] total estimado {} ofertas en {} paginas",
            self.portal,
            total,
            pages,
        )

        seen: set[str] = set()
        all_offers: list[JobOffer] = []
        current_html = first_html

        for page in range(pages):
            if page > 0:
                time.sleep(random.uniform(1.5, 3.0))
                page_url = self._with_pagination(base_url, total, page)
                current_html = self._fetch_with_retry(page_url)
            for offer in self.parse(current_html):
                if offer.external_id not in seen:
                    seen.add(offer.external_id)
                    all_offers.append(offer)
            logger.debug(
                "[{}] pagina {}/{} -> {} acumuladas",
                self.portal,
                page + 1,
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

    @staticmethod
    def _extract_total(soup: BeautifulSoup) -> int:
        """De "Empleos 1 a 20 de 23" extrae 23. Si no, asume 20."""
        text = soup.get_text(" ", strip=True)
        match = re.search(r"de\s+([\d.,]+)", text)
        if not match:
            return 20
        raw = re.sub(r"[.,]", "", match.group(1))
        try:
            return int(raw)
        except ValueError:
            return 20

    @staticmethod
    def _with_pagination(base_url: str, total: int, page: int) -> str:
        """Construye ?t=<total>&np=<page> preservando query existente."""
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        query["t"] = [str(total)]
        query["np"] = [str(page)]
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
