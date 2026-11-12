"""Tests del scraper de Buscojobs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from job_watcher.scrapers.buscojobs import BuscojobsScraper

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "buscojobs_listado.html"


def _load_fixture() -> str:
    return _FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_filters_out_caracas_offer() -> None:
    offers = BuscojobsScraper().parse(_load_fixture())
    assert len(offers) == 2
    ids = [o.external_id for o in offers]
    assert "1479003" not in ids
    assert ids == ["1479001", "1479002"]


def test_parse_first_offer_fields() -> None:
    offers = BuscojobsScraper().parse(_load_fixture())
    first = offers[0]
    assert first.portal == "buscojobs"
    assert first.title == "Asesor de Ventas - Sambil Margarita"
    assert first.company == "Nappi Metais"
    assert "Sambil" in first.location or "Porlamar" in first.location
    assert (
        first.url
        == "https://ve.buscojobs.com/asesor-de-ventas-sambil-margarita-en-nueva-esparta-ID-1479001"
    )
    assert first.published_at == datetime(2026, 11, 10, 14, 30, tzinfo=UTC)


def test_es_de_la_isla_positive_match() -> None:
    raw = {
        "Departamento": {"Nombre": "Nueva Esparta"},
        "Descripcion": "Sambil Margarita, turno completo",
        "CargoVacante": "Asesor",
        "PermiteTeletrabajo": 0,
    }
    assert BuscojobsScraper._es_de_la_isla(raw) is True


def test_es_de_la_isla_negative_match() -> None:
    raw = {
        "Departamento": {"Nombre": "Nueva Esparta"},
        "Descripcion": "Country Finance Manager - Caracas",
        "CargoVacante": "Manager",
        "PermiteTeletrabajo": 0,
    }
    assert BuscojobsScraper._es_de_la_isla(raw) is False


def test_es_de_la_isla_no_match_returns_false() -> None:
    raw = {
        "Departamento": {"Nombre": "Nueva Esparta"},
        "Descripcion": "Buscamos profesional proactivo.",
        "CargoVacante": "Analista",
        "PermiteTeletrabajo": 0,
    }
    assert BuscojobsScraper._es_de_la_isla(raw) is False


def test_es_de_la_isla_remote_from_venezuela_ok() -> None:
    raw = {
        "Departamento": {"Nombre": "Venezuela"},
        "Descripcion": "Remoto desde Margarita",
        "CargoVacante": "Analista",
        "PermiteTeletrabajo": 1,
    }
    assert BuscojobsScraper._es_de_la_isla(raw) is True


def test_es_de_la_isla_remote_without_match_rejected() -> None:
    raw = {
        "Departamento": {"Nombre": "Venezuela"},
        "Descripcion": "Trabajo remoto desde cualquier lugar",
        "CargoVacante": "Analista",
        "PermiteTeletrabajo": 1,
    }
    assert BuscojobsScraper._es_de_la_isla(raw) is False


def test_parse_date_discards_whatjobs_harvest() -> None:
    raw = {"Fuente": "Whatjobs_Ppc", "FechaInicio": "2026-11-12T00:00:00.000Z"}
    assert BuscojobsScraper._parse_date(raw) is None


def test_parse_date_native_ok() -> None:
    raw = {"Fuente": None, "FechaInicio": "2026-11-10T14:30:00.000Z"}
    assert BuscojobsScraper._parse_date(raw) == datetime(2026, 11, 10, 14, 30, tzinfo=UTC)


def test_parse_date_invalid_returns_none() -> None:
    raw = {"Fuente": None, "FechaInicio": "no-es-fecha"}
    assert BuscojobsScraper._parse_date(raw) is None


def test_run_fetches_and_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.text = _load_fixture()
    mock_response.raise_for_status.return_value = None
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr("requests.Session.get", mock_get)

    offers = BuscojobsScraper().run("")
    assert len(offers) == 2
    assert mock_get.call_count == 1
