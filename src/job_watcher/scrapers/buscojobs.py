"""Scraper de Buscojobs Venezuela (ve.buscojobs.com)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, ClassVar

from bs4 import BeautifulSoup
from loguru import logger

from job_watcher.models import JobOffer
from job_watcher.scrapers.base import BaseScraper


class BuscojobsScraper(BaseScraper):
    """Scraper de Buscojobs con filtro geografico en 3 capas."""

    portal = "buscojobs"
    BASE_URL = "https://ve.buscojobs.com/"
    ESTADOS: ClassVar[dict[str, str]] = {
        "nueva-esparta": "ofertas/rd475/trabajo-en-nueva-esparta",
    }
    ISLA_POSITIVO: ClassVar[tuple[str, ...]] = (
        "nueva esparta",
        "isla de margarita",
        "margarita",
        "porlamar",
        "pampatar",
        "sambil",
        "maneiro",
        "marino",
        "mariño",
        "la asuncion",
        "la asunción",
        "juan griego",
        "el yaque",
        "guacuco",
        "playa el angel",
        "playa el ángel",
        "costa azul",
        "los robles",
        "arismendi",
        "antolin del campo",
        "antolín del campo",
        "tubores",
        "macanao",
        "villalba",
        "gomez",
        "gómez",
        "marcano",
        "diaz",
        "díaz",
        "garcia",
        "garcía",
        "libertador",
    )
    CIUDADES_NEGATIVAS: ClassVar[tuple[str, ...]] = (
        "caracas",
        "distrito capital",
        "barcelona",
        "puerto la cruz",
        "valencia",
        "maracaibo",
        "maracay",
        "barquisimeto",
        "miranda",
        "zulia",
        "carabobo",
        "lara",
        "anzoategui",
        "anzátegui",
        "tachira",
        "táchira",
        "latin america",
    )

    def __init__(self, estado: str = "nueva-esparta", **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        if estado not in self.ESTADOS:
            raise ValueError(f"estado no soportado: {estado}")
        self._estado = estado

    def parse(self, html: str) -> list[JobOffer]:
        """Extrae ofertas del HTML parseando __NEXT_DATA__."""
        soup = BeautifulSoup(html, "lxml")
        raw_offers = self._extract_next_data(soup)
        if not raw_offers:
            logger.warning("[{}] sin ofertas en __NEXT_DATA__", self.portal)
            return []

        offers: list[JobOffer] = []
        for raw in raw_offers:
            if not self._es_de_la_isla(raw):
                continue
            offer = self._build_offer(raw)
            if offer is not None:
                offers.append(offer)

        logger.info(
            "[{}] {} brutas -> {} de la isla",
            self.portal,
            len(raw_offers),
            len(offers),
        )
        return offers

    @staticmethod
    def _extract_next_data(soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Navega __NEXT_DATA__ hasta props.pageProps.resultadosIniciales.ofertas."""
        script = soup.find("script", id="__NEXT_DATA__")
        if script is None or not script.string:
            return []
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return []
        ofertas = (
            data.get("props", {})
            .get("pageProps", {})
            .get("resultadosIniciales", {})
            .get("ofertas", [])
        )
        if not isinstance(ofertas, list):
            return []
        return [o for o in ofertas if isinstance(o, dict)]

    @classmethod
    def _es_de_la_isla(cls, raw: dict[str, Any]) -> bool:
        """3 capas: cubo Venezuela, NE con gazetteer, otros estados."""
        depto = str((raw.get("Departamento") or {}).get("Nombre", ""))
        remoto = bool(raw.get("PermiteTeletrabajo", 0))
        cargo = str(raw.get("CargoVacante", "")).lower()
        desc = str(raw.get("Descripcion", "")).lower()
        haystack = f"{cargo} {desc}"

        tiene_positivo = any(kw in haystack for kw in cls.ISLA_POSITIVO)
        tiene_negativo = any(kw in haystack for kw in cls.CIUDADES_NEGATIVAS)

        if depto == "Venezuela":
            return remoto and tiene_positivo
        if depto == "Nueva Esparta":
            if tiene_positivo:
                return True
            if tiene_negativo:
                return False
            return False
        return False

    @classmethod
    def _build_offer(cls, raw: dict[str, Any]) -> JobOffer | None:
        external_id = str(raw.get("IdOferta", "")).strip()
        title = str(raw.get("CargoVacante", "")).strip()
        if not external_id or not title:
            return None

        # Generar slug para la URL de detalle
        depto = str((raw.get("Departamento") or {}).get("Nombre", "Venezuela"))
        title_slug = cls._slugify(title)
        depto_slug = cls._slugify(depto)
        url = f"{cls.BASE_URL}{title_slug}-en-{depto_slug}-ID-{external_id}"

        company = str(raw.get("NombreEmpresa") or "").strip()
        location = cls._infer_location(raw)
        published_at = cls._parse_date(raw)
        descripcion = str(raw.get("Descripcion") or "").strip()

        return JobOffer(
            portal=cls.portal,
            title=title,
            company=company,
            location=location,
            url=url,
            external_id=external_id,
            published_at=published_at,
            raw_text=descripcion,
        )

    @staticmethod
    def _slugify(text: str) -> str:
        """Convierte un texto a slug para URLs (minúsculas, sin acentos, guiones)."""
        import re
        import unicodedata

        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^\w\s-]", "", text).strip().lower()
        return re.sub(r"[-\s]+", "-", text)

    @classmethod
    def _infer_location(cls, raw: dict[str, Any]) -> str:
        """Intenta extraer la ciudad real del gazetteer; fallback a NE."""
        cargo = str(raw.get("CargoVacante", "")).lower()
        desc = str(raw.get("Descripcion", "")).lower()
        haystack = f"{cargo} {desc}"
        ciudades = {
            "porlamar": "Porlamar",
            "pampatar": "Pampatar",
            "la asuncion": "La Asuncion",
            "la asunción": "La Asunción",
            "juan griego": "Juan Griego",
            "el yaque": "El Yaque",
            "sambil": "Porlamar",
            "playa el angel": "Playa El Angel",
            "playa el ángel": "Playa El Angel",
        }
        for key, city in ciudades.items():
            if key in haystack:
                return f"{city}, Nueva Esparta"
        return "Nueva Esparta"

    @staticmethod
    def _parse_date(raw: dict[str, Any]) -> datetime | None:
        """Parsea FechaInicio ISO. Descarta fechas de cosecha de Whatjobs_Ppc."""
        fecha_str = str(raw.get("FechaInicio") or "")
        if not fecha_str:
            return None
        if raw.get("Fuente") == "Whatjobs_Ppc" and fecha_str.endswith("T00:00:00.000Z"):
            return None
        try:
            return datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))
        except ValueError:
            return None

    def run(self, url: str) -> list[JobOffer]:
        """Override: sin paginacion (1 GET por corrida)."""
        base_url = url or (self.BASE_URL + self.ESTADOS[self._estado])
        html = self.fetch(base_url)
        offers = self.parse(html)
        logger.info("[{}] total recolectadas {}", self.portal, len(offers))
        return offers
