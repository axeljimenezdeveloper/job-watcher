"""Scraper de Emplate Venezuela (www.empleate.com)."""

from __future__ import annotations

import random
import re
import time
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import requests
from bs4 import BeautifulSoup, Tag
from loguru import logger

from job_watcher.models import JobOffer
from job_watcher.scrapers.base import BaseScraper


class EmpleateScraper(BaseScraper):
    """Extrae ofertas de www.empleate.com filtrando por estado."""

    portal = "empleate"
    # BASE_URL incluye /1/ para que run_multi_estado apunte a pagina 1
    BASE_URL = "https://www.empleate.com/venezuela/ofertas/empleos_encontrados/1/"
    BASE_URL_PREFIX = "https://www.empleate.com/venezuela/ofertas/empleos_encontrados/"
    ESTADOS: ClassVar[dict[str, str]] = {
        "nueva-esparta": "trabajos-en-venezuela-en-el-estado-nueva_esparta",
        "distrito-capital": "trabajos-en-venezuela-en-el-estado-distrito_capital",
        "miranda": "trabajos-en-venezuela-en-el-estado-miranda",
        "carabobo": "trabajos-en-venezuela-en-el-estado-carabobo",
        "zulia": "trabajos-en-venezuela-en-el-estado-zulia",
    }

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
        """Parsea una pagina de listado. Excluye tarjetas destacadas."""
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("div.card.w-100")
        if not cards:
            logger.warning("[{}] no se encontraron <div.card.w-100>", self.portal)
            return []

        offers: list[JobOffer] = []
        for card in cards:
            if not isinstance(card, Tag):
                continue
            classes = set(card.get("class") or [])
            if "card-desta" in classes:
                continue
            offer = self._parse_card(card)
            if offer is not None:
                offers.append(offer)
        return offers

    def _parse_card(self, card: Tag) -> JobOffer | None:
        anchor = card.select_one('a.none-decoration[href*="/ofertas/empleo/"]')
        if anchor is None:
            return None
        href = str(anchor.get("href", "")).split("#")[0]
        if not href:
            return None

        external_id = self._extract_id(href)
        if not external_id:
            return None

        title_el = card.select_one("span.cargo-titulo")
        if title_el is None:
            return None
        title = str(title_el.get_text(" ", strip=True))
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
    def _extract_id(href: str) -> str:
        match = re.search(r"/ofertas/empleo/(\d+)/", href)
        return match.group(1) if match else ""

    @staticmethod
    def _extract_company(card: Tag) -> str:
        """Texto directo del <p>, excluyendo <span class=obser>."""
        p = card.select_one("p.nombre-empresa")
        if p is None:
            return ""
        direct = [
            str(t).strip() for t in p.find_all(string=True, recursive=False) if str(t).strip()
        ]
        if direct:
            return " ".join(direct)
        return str(p.get_text(" ", strip=True))

    @staticmethod
    def _extract_location(card: Tag) -> str:
        span = card.select_one("span.ubicacion-empresa")
        if span is None:
            return ""
        return str(span.get_text(" ", strip=True))

    @staticmethod
    def _extract_snippet(card: Tag) -> str:
        p = card.select_one("p.descripcion-cargo")
        if p is None:
            return ""
        return str(p.get_text(" ", strip=True))

    @classmethod
    def _extract_published(cls, card: Tag) -> datetime | None:
        p = card.select_one("p.fecha-publi")
        if p is None:
            return None
        return cls._parse_date(p.get_text(" ", strip=True))

    @staticmethod
    def _parse_date(text: str) -> datetime | None:
        """Convierte "Hace X hrs/días/min", "Ayer", "el 27 de Octubre" a datetime."""
        normalized = " ".join(text.lower().split())
        normalized = re.sub(r"^publicado\s+", "", normalized)
        now = datetime.now(UTC)

        m = re.search(r"hace\s+(\d+)\s+(hrs?\.?|horas?|min\.?|minutos?|d[ií]as?)", normalized)
        if m:
            amount = int(m.group(1))
            unit = m.group(2)
            if unit.startswith("h"):
                return now - timedelta(hours=amount)
            if unit.startswith("min"):
                return now - timedelta(minutes=amount)
            if unit.startswith("d"):
                return now - timedelta(days=amount)

        if normalized == "ayer":
            return now - timedelta(days=1)

        m = re.search(r"el\s+(\d{1,2})\s+de\s+(\w+)", normalized)
        if m:
            day = int(m.group(1))
            month_name = m.group(2)
            months = {
                "enero": 1,
                "febrero": 2,
                "marzo": 3,
                "abril": 4,
                "mayo": 5,
                "junio": 6,
                "julio": 7,
                "agosto": 8,
                "septiembre": 9,
                "octubre": 10,
                "noviembre": 11,
                "diciembre": 12,
            }
            month = months.get(month_name)
            if month is not None:
                year = now.year if month <= now.month else now.year - 1
                try:
                    return datetime(year, month, day, tzinfo=UTC)
                except ValueError:
                    return None

        return None

    @staticmethod
    def _extract_total(soup: BeautifulSoup) -> int:
        strong = soup.select_one("div.ordenador strong")
        if strong is None:
            return 15
        try:
            return int(strong.get_text(strip=True))
        except ValueError:
            return 15

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

    def run(self, url: str) -> list[JobOffer]:
        """Override: pagina por estado con limite max_pages."""
        first_html = self._fetch_with_retry(url)
        first_soup = BeautifulSoup(first_html, "lxml")
        total = self._extract_total(first_soup)
        pages = min(self._max_pages, max(1, -(-total // 15)))
        logger.info(
            "[{}] total estimado {} ofertas en {} paginas",
            self.portal,
            total,
            pages,
        )

        m = re.search(r"/empleos_encontrados/\d+/(.+)$", url)
        slug = m.group(1) if m else self.ESTADOS[self._estado]

        seen: set[str] = set()
        all_offers: list[JobOffer] = []
        current_html = first_html

        for page in range(1, pages + 1):
            if page > 1:
                time.sleep(random.uniform(1.5, 3.0))
                page_url = f"{self.BASE_URL_PREFIX}{page}/{slug}"
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
