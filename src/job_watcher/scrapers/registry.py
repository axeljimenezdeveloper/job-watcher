"""Registro central de scrapers disponibles."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import cast

from job_watcher.scrapers.base import BaseScraper


def _load_unmejorempleo() -> type[BaseScraper]:
    """Import perezoso: el modulo se resuelve en runtime, no en import-time."""
    module = importlib.import_module("job_watcher.scrapers.unmejorempleo")
    return cast(type[BaseScraper], module.UnMejorEmpleoScraper)


def _load_trabajo_org() -> type[BaseScraper]:
    """Import perezoso del scraper de trabajo.org."""
    module = importlib.import_module("job_watcher.scrapers.trabajo_org")
    return cast(type[BaseScraper], module.TrabajoOrgScraper)


SCRAPERS: dict[str, Callable[[], type[BaseScraper]]] = {
    "trabajo_org": _load_trabajo_org,
    "unmejorempleo": _load_unmejorempleo,
}


def get_scraper(name: str) -> type[BaseScraper]:
    """Resuelve un scraper por nombre. Lanza KeyError si no existe."""
    if name not in SCRAPERS:
        available = ", ".join(sorted(SCRAPERS))
        raise KeyError(f"Scraper desconocido: {name!r}. Disponibles: {available}")
    return SCRAPERS[name]()
