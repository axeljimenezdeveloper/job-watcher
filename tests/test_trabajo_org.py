"""Tests del scraper de Trabajo.org."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from job_watcher.scrapers.trabajo_org import TrabajoOrgScraper

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "trabajo_org_listado.html"


def _load_fixture() -> str:
    return _FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_extracts_three_offers_skipping_alert() -> None:
    offers = TrabajoOrgScraper().parse(_load_fixture())
    assert len(offers) == 3
    ids = [o.external_id for o in offers]
    assert ids == ["2463582860", "2462594730", "2462024186"]


def test_parse_extracts_fields() -> None:
    offers = TrabajoOrgScraper().parse(_load_fixture())
    first = offers[0]
    assert first.portal == "trabajo_org"
    assert first.title == "Oficial Shelter"
    assert first.company == "ReliefWeb"
    assert first.location == "Porlamar, Nueva Esparta State, Venezuela"
    assert first.url == "https://ve.trabajo.org/oferta-4112-9e4df9acda71a62ef4d59fa8ed830c2d"
    assert first.published_at is not None


def test_parse_company_is_coca_cola_for_second() -> None:
    offers = TrabajoOrgScraper().parse(_load_fixture())
    assert offers[1].company == "Coca-Cola FEMSA"
    assert offers[1].title == "Jefe I Ejecucion Preventiva Linea"


def test_parse_returns_empty_when_no_list() -> None:
    assert TrabajoOrgScraper().parse("<html></html>") == []


def test_parse_relative_date_hours() -> None:
    now = datetime.now(UTC)
    result = TrabajoOrgScraper._parse_relative_date("Hace 13 horas")
    assert result is not None
    assert abs((now - result) - timedelta(hours=13)) < timedelta(minutes=1)


def test_parse_relative_date_invalid_returns_none() -> None:
    assert TrabajoOrgScraper._parse_relative_date("sin fecha") is None


def test_extract_total_from_title() -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_load_fixture(), "lxml")
    assert TrabajoOrgScraper._extract_total(soup) == 85


def test_with_pagination_adds_page_param() -> None:
    url = TrabajoOrgScraper._with_pagination("https://ve.trabajo.org/empleo/Nueva+Esparta", page=3)
    assert "page=3" in url


def test_run_fetches_first_page_and_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture tiene 85 en title → 5 paginas. Forzamos total=20 para 1 sola pagina."""
    mock_response = MagicMock()
    mock_response.text = _load_fixture()
    mock_response.raise_for_status.return_value = None
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr("job_watcher.scrapers.base.requests.get", mock_get)
    monkeypatch.setattr(TrabajoOrgScraper, "_extract_total", staticmethod(lambda soup: 20))

    offers = TrabajoOrgScraper().run("")
    assert len(offers) == 3
    assert mock_get.call_count == 1


def test_run_paginates_when_total_is_large(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con total=85 debe hacer 5 requests (1 + 4 paginadas)."""
    mock_response = MagicMock()
    mock_response.text = _load_fixture()
    mock_response.raise_for_status.return_value = None
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr("job_watcher.scrapers.base.requests.get", mock_get)

    offers = TrabajoOrgScraper(max_pages=10).run("")
    # 5 paginas pero mismo fixture en todas -> 3 ofertas unicas
    assert len(offers) == 3
    assert mock_get.call_count == 5
