"""Tests del scraper de Trabajos Diarios."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from job_watcher.scrapers.trabajosdiarios import TrabajosDiariosScraper

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "trabajosdiarios_listado.html"


def _load_fixture() -> str:
    return _FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_extracts_two_offers_skipping_chip_and_ads() -> None:
    offers = TrabajosDiariosScraper().parse(_load_fixture())
    assert len(offers) == 2
    assert [o.external_id for o in offers] == ["3107341", "3098671"]


def test_parse_extracts_fields_first() -> None:
    offers = TrabajosDiariosScraper().parse(_load_fixture())
    first = offers[0]
    assert first.portal == "trabajosdiarios"
    assert first.title == "Asesor de ventas-Sambil Margarita"
    assert first.company == "RADICAL"
    assert first.location == "Porlamar, Nueva Esparta"
    assert "3107341" in first.url
    assert first.published_at == datetime(2026, 11, 4, tzinfo=UTC)


def test_parse_extracts_fields_second() -> None:
    offers = TrabajosDiariosScraper().parse(_load_fixture())
    second = offers[1]
    assert second.title == "Vendedor en Margarita"
    assert second.company == "CALA GESTION 21"
    assert second.location == "porlarmar, Nueva Esparta"
    assert second.published_at == datetime(2026, 10, 13, tzinfo=UTC)


def test_parse_returns_empty_when_no_list() -> None:
    assert TrabajosDiariosScraper().parse("<html></html>") == []


def test_parse_date_valid() -> None:
    assert TrabajosDiariosScraper._parse_date("04/11/2026") == datetime(2026, 11, 4, tzinfo=UTC)


def test_parse_date_invalid_returns_none() -> None:
    assert TrabajosDiariosScraper._parse_date("sin fecha") is None
    assert TrabajosDiariosScraper._parse_date("99/99/9999") is None


def test_extract_id_from_button() -> None:
    from bs4 import BeautifulSoup

    html = '<div class="card"><button class="btn-favorito" data-oferta-id="999">x</button></div>'
    soup = BeautifulSoup(html, "lxml")
    card = soup.select_one("div.card")
    assert card is not None
    assert TrabajosDiariosScraper._extract_id(card, "") == "999"


def test_extract_id_falls_back_to_url() -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup('<div class="card"></div>', "lxml")
    card = soup.select_one("div.card")
    assert card is not None
    ext = TrabajosDiariosScraper._extract_id(
        card, "https://ve.trabajosdiarios.com/trabajo/1234/slug"
    )
    assert ext == "1234"


def test_run_fetches_and_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.text = _load_fixture()
    mock_response.raise_for_status.return_value = None
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr("requests.Session.get", mock_get)

    offers = TrabajosDiariosScraper().run("")
    assert len(offers) == 2
    assert mock_get.call_count == 1
