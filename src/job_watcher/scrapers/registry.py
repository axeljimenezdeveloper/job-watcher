"""Registro central de scrapers disponibles."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import cast

from job_watcher.scrapers.base import BaseScraper


def _load_buscojobs() -> type[BaseScraper]:
    module = importlib.import_module("job_watcher.scrapers.buscojobs")
    return cast(type[BaseScraper], module.BuscojobsScraper)


def _load_computrabajo() -> type[BaseScraper]:
    module = importlib.import_module("job_watcher.scrapers.computrabajo")
    return cast(type[BaseScraper], module.ComputrabajoScraper)


def _load_trabajosdiarios() -> type[BaseScraper]:
    module = importlib.import_module("job_watcher.scrapers.trabajosdiarios")
    return cast(type[BaseScraper], module.TrabajosDiariosScraper)


def _load_trabajo_org() -> type[BaseScraper]:
    module = importlib.import_module("job_watcher.scrapers.trabajo_org")
    return cast(type[BaseScraper], module.TrabajoOrgScraper)


def _load_unmejorempleo() -> type[BaseScraper]:
    module = importlib.import_module("job_watcher.scrapers.unmejorempleo")
    return cast(type[BaseScraper], module.UnMejorEmpleoScraper)


SCRAPERS: dict[str, Callable[[], type[BaseScraper]]] = {
    "buscojobs": _load_buscojobs,
    "computrabajo": _load_computrabajo,
    "trabajosdiarios": _load_trabajosdiarios,
    "trabajo_org": _load_trabajo_org,
    "unmejorempleo": _load_unmejorempleo,
}


def get_scraper(name: str) -> type[BaseScraper]:
    """Resuelve un scraper por nombre. Lanza KeyError si no existe."""
    if name not in SCRAPERS:
        available = ", ".join(sorted(SCRAPERS))
        raise KeyError(f"Scraper desconocido: {name!r}. Disponibles: {available}")
    return SCRAPERS[name]()
