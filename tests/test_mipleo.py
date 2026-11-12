"""Tests del scraper de Mipleo."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from job_watcher.scrapers.mipleo import MipleoScraper

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mipleo_listado.html"


def _load_fixture() -> str:
    return _FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_extracts_three_offers_skipping_ad() -> None:
    offers = MipleoScraper().parse(_load_fixture())
    assert len(offers) == 3
    assert [o.external_id for o in offers] == ["312273", "312235", "312185"]


def test_parse_first_offer_fields() -> None:
    offers = MipleoScraper().parse(_load_fixture())
    first = offers[0]
    assert first.portal == "mipleo"
    assert first.title == "Gerente de administración"
    assert first.company == ""
    assert first.location == "Maneiro, Nueva Esparta"
    assert first.url.endswith("gerente-de-administracion-312273.html")
    assert first.published_at is not None


def test_parse_second_offer_company() -> None:
    offers = MipleoScraper().parse(_load_fixture())
    second = offers[1]
    assert second.title == "Mecánico Integral Diesel y Gasolina"
    assert second.company == "GRUPO LEIROS"
    assert second.location == "Mariño, Nueva Esparta"


def test_parse_returns_empty_when_no_cards() -> None:
    assert MipleoScraper().parse("<html></html>") == []


def test_extract_id_regex() -> None:
    url = "https://www.mipleo.com.ve/ofertas-de-trabajo/oferta-de-trabajo-en-nueva-esparta/gerente-de-administracion-312273.html"
    assert MipleoScraper._extract_id(url) == "312273"


def test_extract_total() -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_load_fixture(), "lxml")
    assert MipleoScraper._extract_total(soup) == 18


def test_extract_total_fallback() -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<html></html>", "lxml")
    assert MipleoScraper._extract_total(soup) == 20


def test_extract_published_iso_with_offset() -> None:
    offers = MipleoScraper().parse(_load_fixture())
    first_date = offers[0].published_at
    assert first_date is not None
    assert first_date.year == 2026
    assert first_date.month == 11
    assert first_date.day == 11
    # Verifica offset -04:00: hora 12:20 local = 16:20 UTC
    assert first_date.astimezone(UTC).hour == 16


def test_extract_slug_from_url() -> None:
    url = "https://www.mipleo.com.ve/ofertas-de-trabajo/empleos-nueva-esparta?pag=2"
    assert MipleoScraper._extract_slug(url) == "nueva-esparta"


def test_with_pagination_builds_url() -> None:
    url = MipleoScraper()._with_pagination("nueva-esparta", 3)
    assert "empleos-nueva-esparta" in url
    assert "pag=3" in url
    assert "ord=da" in url


def test_run_fetches_first_page(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.text = _load_fixture()
    mock_response.raise_for_status.return_value = None
    monkeypatch.setattr(
        "job_watcher.scrapers.base.requests.get",
        MagicMock(return_value=mock_response),
    )

    # total=18 => 1 sola pagina, no paginamos
    url = "https://www.mipleo.com.ve/ofertas-de-trabajo/empleos-nueva-esparta"
    offers = MipleoScraper().run(url)
    assert len(offers) == 3


def test_run_paginates_when_total_is_large(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con total=518 => 5 paginas (limitado por max_pages=5)."""
    big_fixture = _load_fixture().replace("<i>18</i>", "<i>518</i>")
    mock_response = MagicMock()
    mock_response.text = big_fixture
    mock_response.raise_for_status.return_value = None
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr("job_watcher.scrapers.base.requests.get", mock_get)

    url = "https://www.mipleo.com.ve/ofertas-de-trabajo/empleos-distrito-capital"
    offers = MipleoScraper(max_pages=5).run(url)
    # 5 paginas x 3 ofertas unicas del fixture = 3 (dedup por external_id)
    assert len(offers) == 3
    assert mock_get.call_count == 5
