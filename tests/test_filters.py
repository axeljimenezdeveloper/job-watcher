"""Tests de los filtros de perfil."""

from __future__ import annotations

from job_watcher.config import Profile
from job_watcher.filters import ProfileFilter, filter_offers, normalize
from job_watcher.models import JobOffer


def _profile(**overrides: object) -> Profile:
    defaults: dict[str, object] = {
        "name": "test",
        "enabled": True,
        "must_match_any": ["inventario", "logistica"],
        "must_not_match": ["senior", "gerente"],
        "locations_any": ["Nueva Esparta", "Porlamar"],
        "local_locations": [],
        "remote_keywords": [],
    }
    defaults.update(overrides)
    return Profile(**defaults)  # type: ignore[arg-type]


def _offer(**overrides: object) -> JobOffer:
    defaults: dict[str, object] = {
        "portal": "unmejorempleo",
        "title": "Analista de Inventarios",
        "company": "ACME",
        "location": "Porlamar, Nueva Esparta",
        "url": "https://example.com/1",
        "external_id": "1",
        "raw_text": "Control de inventario y logistica.",
    }
    defaults.update(overrides)
    return JobOffer(**defaults)  # type: ignore[arg-type]


def test_normalize_removes_accents_and_lowercases() -> None:
    assert normalize("Gestión de Inventario") == "gestion de inventario"
    assert normalize("  LOGÍSTICA  ") == "logistica"
    assert normalize("Añadir") == "anadir"


def test_match_by_keyword_in_title() -> None:
    assert ProfileFilter(_profile()).matches(_offer(title="Analista de Inventarios")) is True


def test_match_by_keyword_in_raw_text_only() -> None:
    offer = _offer(title="Cargo generico", raw_text="Buscamos alguien con logistica.")
    assert ProfileFilter(_profile()).matches(offer) is True


def test_match_case_and_accent_insensitive() -> None:
    offer = _offer(title="GESTIÓN DE INVENTARIO", raw_text="")
    assert ProfileFilter(_profile()).matches(offer) is True


def test_no_keyword_no_match() -> None:
    offer = _offer(title="Camarera", raw_text="Limpiar habitaciones.")
    assert ProfileFilter(_profile()).matches(offer) is False


def test_exclusion_blocks_match() -> None:
    offer = _offer(title="Analista de Inventarios Senior")
    assert ProfileFilter(_profile()).matches(offer) is False


def test_exclusion_in_raw_text_blocks() -> None:
    offer = _offer(raw_text="Buscamos gerente de inventario.")
    assert ProfileFilter(_profile()).matches(offer) is False


def test_location_must_match() -> None:
    offer = _offer(location="Caracas, Distrito Capital")
    assert ProfileFilter(_profile()).matches(offer) is False


def test_empty_keywords_matches_anything() -> None:
    profile = _profile(must_match_any=[])
    offer = _offer(title="Camarera", location="Porlamar")
    assert ProfileFilter(profile).matches(offer) is True


def test_empty_exclusions() -> None:
    profile = _profile(must_not_match=[])
    offer = _offer(title="Analista de Inventarios Senior")
    assert ProfileFilter(profile).matches(offer) is True


def test_empty_locations() -> None:
    profile = _profile(locations_any=[])
    offer = _offer(location="Caracas")
    assert ProfileFilter(profile).matches(offer) is True


def test_filter_offers_returns_only_matches() -> None:
    profile = _profile()
    offers = [
        _offer(external_id="1", title="Analista de Inventarios"),
        _offer(
            external_id="2",
            title="Camarera",
            location="Porlamar",
            raw_text="Limpiar habitaciones.",
        ),
        _offer(external_id="3", title="Gerente de Inventario"),
    ]
    result = filter_offers(offers, profile)
    assert len(result) == 1
    assert result[0].external_id == "1"


def test_remote_offer_from_other_state_passes() -> None:
    profile = _profile(
        must_match_any=["frontend"],
        must_not_match=[],
        locations_any=[],
        local_locations=["Nueva Esparta"],
        remote_keywords=["remoto", "home office"],
    )
    offer = _offer(
        title="Frontend Developer",
        location="Caracas, Distrito Capital",
        raw_text="Trabajo 100% remoto.",
    )
    assert ProfileFilter(profile).matches(offer) is True


def test_local_offer_passes_without_remote_keyword() -> None:
    profile = _profile(
        must_match_any=["frontend"],
        must_not_match=[],
        locations_any=[],
        local_locations=["Nueva Esparta", "Porlamar"],
        remote_keywords=["remoto"],
    )
    offer = _offer(
        title="Frontend Developer",
        location="Porlamar, Nueva Esparta",
        raw_text="Trabajo presencial en oficina.",
    )
    assert ProfileFilter(profile).matches(offer) is True


def test_presencial_from_other_state_fails() -> None:
    profile = _profile(
        must_match_any=["frontend"],
        must_not_match=[],
        locations_any=[],
        local_locations=["Nueva Esparta"],
        remote_keywords=["remoto", "home office"],
    )
    offer = _offer(
        title="Frontend Developer",
        location="Valencia, Carabobo",
        raw_text="Trabajo presencial en oficina.",
    )
    assert ProfileFilter(profile).matches(offer) is False


def test_max_age_filters_old_offers() -> None:
    from datetime import UTC, datetime, timedelta

    profile = _profile(max_age_days=7)
    old_date = datetime.now(UTC) - timedelta(days=10)
    offer = _offer(published_at=old_date)
    assert ProfileFilter(profile).matches(offer) is False


def test_max_age_allows_recent() -> None:
    from datetime import UTC, datetime, timedelta

    profile = _profile(max_age_days=7)
    recent = datetime.now(UTC) - timedelta(days=2)
    offer = _offer(published_at=recent)
    assert ProfileFilter(profile).matches(offer) is True


def test_max_age_allows_none_date() -> None:
    profile = _profile(max_age_days=7)
    offer = _offer(published_at=None)
    assert ProfileFilter(profile).matches(offer) is True


def test_max_age_disabled_allows_old() -> None:
    from datetime import UTC, datetime, timedelta

    profile = _profile(max_age_days=0)
    old = datetime.now(UTC) - timedelta(days=30)
    offer = _offer(published_at=old)
    assert ProfileFilter(profile).matches(offer) is True
