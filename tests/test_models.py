"""Tests del modelo JobOffer."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from job_watcher.models import JobOffer


def _offer(**overrides: object) -> JobOffer:
    defaults: dict[str, object] = {
        "portal": "unmejorempleo",
        "title": "Analista de Inventarios",
        "company": "ACME",
        "location": "Porlamar, Nueva Esparta",
        "url": "https://example.com/oferta/1",
        "external_id": "abc123",
        "published_at": datetime(2026, 1, 15, tzinfo=UTC),
        "raw_text": "Descripcion de la oferta",
    }
    defaults.update(overrides)
    return JobOffer(**defaults)  # type: ignore[arg-type]


def test_offer_creates_valid_instance() -> None:
    offer = _offer()
    assert offer.portal == "unmejorempleo"
    assert offer.title == "Analista de Inventarios"
    assert offer.company == "ACME"
    assert offer.url == "https://example.com/oferta/1"


def test_fingerprint_is_stable() -> None:
    a = _offer()
    b = _offer()
    assert a.fingerprint == b.fingerprint
    assert len(a.fingerprint) == 64


def test_fingerprint_changes_with_external_id() -> None:
    a = _offer(external_id="abc123")
    b = _offer(external_id="xyz789")
    assert a.fingerprint != b.fingerprint


def test_fingerprint_falls_back_to_url() -> None:
    a = _offer(external_id="", url="https://example.com/a")
    b = _offer(external_id="", url="https://example.com/b")
    assert a.fingerprint != b.fingerprint


@pytest.mark.parametrize("field_name", ["portal", "title", "url"])
def test_empty_required_fields_raise(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        _offer(**{field_name: ""})
