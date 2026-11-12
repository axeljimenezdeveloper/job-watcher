"""Filtros de perfil para ofertas de empleo."""

from __future__ import annotations

import unicodedata

from job_watcher.config import Profile
from job_watcher.models import JobOffer


def _normalize(text: str) -> str:
    """Lowercase + sin tildes + espacios colapsados."""
    text = text.lower().strip()
    decomposed = unicodedata.normalize("NFD", text)
    without_accents = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(without_accents.split())


class ProfileFilter:
    """Evalua si una JobOffer satisface un Profile."""

    def __init__(self, profile: Profile) -> None:
        self._profile = profile
        self._keywords = [_normalize(k) for k in profile.must_match_any]
        self._exclusions = [_normalize(e) for e in profile.must_not_match]
        self._locations = [_normalize(loc) for loc in profile.locations_any]

    def _has_exclusion(self, haystack: str) -> bool:
        """True si alguna exclusion aparece en el haystack."""
        return bool(self._exclusions) and any(exc in haystack for exc in self._exclusions)

    def _has_keyword(self, haystack: str) -> bool:
        """True si hay al menos un keyword (o no hay keywords)."""
        if not self._keywords:
            return True
        return any(kw in haystack for kw in self._keywords)

    def _has_location(self, haystack: str) -> bool:
        """True si hay al menos una ubicacion (o no hay ubicaciones)."""
        if not self._locations:
            return True
        return any(loc in haystack for loc in self._locations)

    def matches(self, offer: JobOffer) -> bool:
        """True si la oferta cumple todas las reglas del perfil."""
        haystack = _normalize(f"{offer.title} {offer.raw_text} {offer.location}")
        return (
            not self._has_exclusion(haystack)
            and self._has_keyword(haystack)
            and self._has_location(haystack)
        )


def filter_offers(offers: list[JobOffer], profile: Profile) -> list[JobOffer]:
    """Filtra una lista de ofertas contra un perfil."""
    matcher = ProfileFilter(profile)
    return [offer for offer in offers if matcher.matches(offer)]
