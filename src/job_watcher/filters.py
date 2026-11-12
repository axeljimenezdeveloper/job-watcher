"""Filtros de perfil para ofertas de empleo."""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime, timedelta

from job_watcher.config import Profile
from job_watcher.models import JobOffer


def normalize(text: str) -> str:
    """Lowercase + sin tildes + espacios colapsados. Publica para reuso."""
    text = text.lower().strip()
    decomposed = unicodedata.normalize("NFD", text)
    without_accents = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(without_accents.split())


class ProfileFilter:
    """Evalua si una JobOffer satisface un Profile."""

    def __init__(self, profile: Profile) -> None:
        self._profile = profile
        self._keywords = [normalize(k) for k in profile.must_match_any]
        self._exclusions = [normalize(e) for e in profile.must_not_match]
        self._locations = [normalize(loc) for loc in profile.locations_any]
        self._local = [normalize(loc) for loc in profile.local_locations]
        self._remote = [normalize(kw) for kw in profile.remote_keywords]
        self._max_age_days = profile.max_age_days

    def _has_exclusion(self, haystack: str) -> bool:
        return bool(self._exclusions) and any(exc in haystack for exc in self._exclusions)

    def _has_keyword(self, haystack: str) -> bool:
        if not self._keywords:
            return True
        return any(kw in haystack for kw in self._keywords)

    def _has_location(self, haystack: str) -> bool:
        if not self._locations:
            return True
        return any(loc in haystack for loc in self._locations)

    def _is_local(self, haystack: str) -> bool:
        if not self._local:
            return True
        return any(loc in haystack for loc in self._local)

    def _has_remote_keyword(self, haystack: str) -> bool:
        if not self._remote:
            return True
        return any(kw in haystack for kw in self._remote)

    def _is_recent_enough(self, offer: JobOffer) -> bool:
        """True si la oferta es reciente (o no tiene fecha)."""
        if self._max_age_days <= 0:
            return True
        if offer.published_at is None:
            return True
        cutoff = datetime.now(UTC) - timedelta(days=self._max_age_days)
        return offer.published_at >= cutoff

    def matches(self, offer: JobOffer) -> bool:
        """True si la oferta cumple todas las reglas del perfil."""
        if not self._is_recent_enough(offer):
            return False
        haystack = normalize(f"{offer.title} {offer.raw_text} {offer.location}")
        if self._has_exclusion(haystack):
            return False
        if not self._has_keyword(haystack):
            return False
        if not self._has_location(haystack):
            return False
        return self._is_local(haystack) or self._has_remote_keyword(haystack)


def filter_offers(offers: list[JobOffer], profile: Profile) -> list[JobOffer]:
    """Filtra una lista de ofertas contra un perfil."""
    matcher = ProfileFilter(profile)
    return [offer for offer in offers if matcher.matches(offer)]
