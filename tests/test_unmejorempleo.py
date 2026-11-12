"""Tests del scraper de UnMejorEmpleo."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from job_watcher.scrapers.unmejorempleo import UnMejorEmpleoScraper

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "unmejorempleo_listado.html"


def _load_fixture() -> str:
    return _FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_extracts_two_offers_skipping_advert() -> None:
    offers = UnMejorEmpleoScraper().parse(_load_fixture())
    assert len(offers) == 2
    assert offers[0].external_id == "5914683"
    assert offers[0].title == "Camarera de Habitaciones"
    assert offers[0].location == "La Asuncion, Nueva Esparta"
    assert offers[0].published_at == datetime(2026, 11, 11, tzinfo=UTC)
    assert offers[1].external_id == "5919999"
    assert offers[1].title == "Analista de Inventarios"
    assert offers[1].location == "Porlamar, Nueva Esparta"
    assert offers[1].raw_text == "Gestionar inventario y logistica."


def test_parse_returns_empty_when_no_article() -> None:
    assert UnMejorEmpleoScraper().parse("<html></html>") == []


def test_extract_id_pattern() -> None:
    assert UnMejorEmpleoScraper._extract_id("...-5914683.html") == "5914683"
    assert UnMejorEmpleoScraper._extract_id("...sin-id.html") == ""


def test_split_location_with_and_without_pipe() -> None:
    assert UnMejorEmpleoScraper._split_location("Ubicacion: Porlamar | Estado : Nueva Esparta") == (
        "Porlamar",
        "Nueva Esparta",
    )
    assert UnMejorEmpleoScraper._split_location("Ubicacion: Porlamar") == (
        "Porlamar",
        "",
    )


def test_extract_date_handles_invalid() -> None:
    assert UnMejorEmpleoScraper._extract_date("Publicacion: 11/11/2026") == datetime(
        2026, 11, 11, tzinfo=UTC
    )
    assert UnMejorEmpleoScraper._extract_date("sin fecha") is None
    assert UnMejorEmpleoScraper._extract_date("Publicacion: 99/99/9999") is None


def test_run_fetches_first_page_and_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.text = _load_fixture()
    mock_response.raise_for_status.return_value = None
    monkeypatch.setattr(
        "requests.Session.get",
        MagicMock(return_value=mock_response),
    )

    # total=2 => 1 sola pagina, no paginamos
    offers = UnMejorEmpleoScraper().run(
        "https://www.unmejorempleo.com.ve/empleo-en-nueva-esparta.html"
    )
    assert len(offers) == 2


def test_with_pagination_preserves_existing_query() -> None:
    url = UnMejorEmpleoScraper._with_pagination("https://x.test/list?f=3", total=42, page=2)
    assert "f=3" in url
    assert "t=42" in url
    assert "np=2" in url
