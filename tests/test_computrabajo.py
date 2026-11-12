"""Tests del scraper de Computrabajo."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from job_watcher.scrapers.computrabajo import ComputrabajoScraper

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "computrabajo_listado.html"


def _load_fixture() -> str:
    return _FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_extracts_two_offers_skipping_adsense() -> None:
    offers = ComputrabajoScraper().parse(_load_fixture())
    assert len(offers) == 2
    ids = [o.external_id for o in offers]
    assert ids == [
        "996E0D634789634C61373E686DCF3405",
        "5203F8B561F07E6A61373E686DCF3405",
    ]


def test_parse_extracts_fields_from_first() -> None:
    offers = ComputrabajoScraper().parse(_load_fixture())
    first = offers[0]
    assert first.portal == "computrabajo"
    assert first.title == "Asesor Optico"
    assert first.company == "Grupo Opticolor"
    assert first.location == "Maneiro, Nueva Esparta"
    assert "#lc=" not in first.url
    assert first.url.endswith("996E0D634789634C61373E686DCF3405")


def test_parse_company_empty_when_not_linked() -> None:
    offers = ComputrabajoScraper().parse(_load_fixture())
    second = offers[1]
    assert second.company == ""
    assert second.title == "Administrativo y Recursos Humanos"


def test_parse_date_ayer() -> None:
    now = datetime.now(UTC)
    offers = ComputrabajoScraper().parse(_load_fixture())
    first_date = offers[0].published_at
    assert first_date is not None
    assert abs((now - first_date) - timedelta(days=1)) < timedelta(minutes=2)


def test_parse_date_hace_2_dias() -> None:
    now = datetime.now(UTC)
    offers = ComputrabajoScraper().parse(_load_fixture())
    second_date = offers[1].published_at
    assert second_date is not None
    assert abs((now - second_date) - timedelta(days=2)) < timedelta(minutes=2)


def test_parse_relative_date_ahora() -> None:
    result = ComputrabajoScraper._parse_relative_date("Ahora")
    assert result is not None
    assert abs(datetime.now(UTC) - result) < timedelta(seconds=5)


def test_parse_relative_date_invalid_returns_none() -> None:
    assert ComputrabajoScraper._parse_relative_date("sin fecha") is None


def test_extract_total_from_h1() -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_load_fixture(), "lxml")
    assert ComputrabajoScraper._extract_total(soup) == 69


def test_extract_total_falls_back_to_20() -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<html></html>", "lxml")
    assert ComputrabajoScraper._extract_total(soup) == 20


def test_with_pagination_builds_p_param() -> None:
    url = ComputrabajoScraper._with_pagination(
        "https://ve.computrabajo.com/empleos-en-nueva-esparta", page=3
    )
    assert "p=3" in url
    assert "page=" not in url


def test_run_fetches_first_page_and_dedupes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fixture tiene 69 en h1, forzamos total=20 para 1 sola pagina."""
    mock_response = MagicMock()
    mock_response.text = _load_fixture()
    mock_response.raise_for_status.return_value = None
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr("job_watcher.scrapers.computrabajo.requests.get", mock_get)
    monkeypatch.setattr(ComputrabajoScraper, "_extract_total", staticmethod(lambda soup: 20))

    offers = ComputrabajoScraper().run("")
    assert len(offers) == 2
    assert mock_get.call_count == 1
