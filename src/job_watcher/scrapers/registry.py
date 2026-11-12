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


SCRAPERS: dict[str, Callable[[], type[BaseScraper]]] = {
    "unmejorempleo": _load_unmejorempleo,
}


def get_scraper(name: str) -> type[BaseScraper]:
    """Resuelve un scraper por nombre. Lanza KeyError si no existe."""
    if name not in SCRAPERS:
        available = ", ".join(sorted(SCRAPERS))
        raise KeyError(f"Scraper desconocido: {name!r}. Disponibles: {available}")
    return SCRAPERS[name]()
