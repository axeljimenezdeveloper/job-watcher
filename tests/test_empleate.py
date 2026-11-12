"""Tests del scraper de Emplate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from job_watcher.scrapers.empleate import EmpleateScraper

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "empleate_listado.html"


def _load_fixture() -> str:
    return _FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_extracts_two_offers_skipping_featured() -> None:
    offers = EmpleateScraper().parse(_load_fixture())
    assert len(offers) == 2
    assert [o.external_id for o in offers] == ["1999496", "1999930"]


def test_parse_first_offer_fields() -> None:
    offers = EmpleateScraper().parse(_load_fixture())
    first = offers[0]
    assert first.portal == "empleate"
    assert first.title == "Asistente Administrativo(a)"
    assert first.company == "Servicios del Frío Friper"
    assert "Nueva Esparta" in first.location
    assert "1999496" in first.url
    assert first.published_at is not None


def test_parse_second_offer_fields() -> None:
    offers = EmpleateScraper().parse(_load_fixture())
    second = offers[1]
    assert second.title == "Asesores(as) de Ventas"
    assert second.company == "Corporación Fibex Telecom"
    assert "Porlamar" in second.location


def test_parse_returns_empty_when_no_cards() -> None:
    assert EmpleateScraper().parse("<html></html>") == []


def test_parse_date_hace_3_hrs() -> None:
    now = datetime.now(UTC)
    result = EmpleateScraper._parse_date("Publicado Hace 3 hrs.")
    assert result is not None
    assert abs((now - result) - timedelta(hours=3)) < timedelta(minutes=2)


def test_parse_date_hace_6_dias() -> None:
    now = datetime.now(UTC)
    result = EmpleateScraper._parse_date("Publicado Hace 6 días")
    assert result is not None
    assert abs((now - result) - timedelta(days=6)) < timedelta(minutes=2)


def test_parse_date_ayer() -> None:
    now = datetime.now(UTC)
    result = EmpleateScraper._parse_date("Publicado Ayer")
    assert result is not None
    assert abs((now - result) - timedelta(days=1)) < timedelta(minutes=2)


def test_parse_date_el_27_de_octubre() -> None:
    result = EmpleateScraper._parse_date("Publicado el 27 de Octubre")
    assert result is not None
    assert result.month == 10
    assert result.day == 27


def test_parse_date_invalid_returns_none() -> None:
    assert EmpleateScraper._parse_date("sin fecha") is None


def test_extract_id_regex() -> None:
    href = "https://www.empleate.com/venezuela/ofertas/empleo/1999496/asistente_administrativo_a/edo_nueva_esparta/"
    assert EmpleateScraper._extract_id(href) == "1999496"


def test_extract_total_from_strong() -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_load_fixture(), "lxml")
    assert EmpleateScraper._extract_total(soup) == 9


def test_extract_total_falls_back_to_15() -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<html></html>", "lxml")
    assert EmpleateScraper._extract_total(soup) == 15


def test_run_fetches_first_page_and_dedupes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_response = MagicMock()
    mock_response.text = _load_fixture()
    mock_response.raise_for_status.return_value = None
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr("job_watcher.scrapers.base.requests.get", mock_get)

    url = "https://www.empleate.com/venezuela/ofertas/empleos_encontrados/1/trabajos-en-venezuela-en-el-estado-nueva_esparta"
    offers = EmpleateScraper().run(url)
    assert len(offers) == 2
    assert mock_get.call_count == 1
