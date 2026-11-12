"""Modelos de dominio del proyecto."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class JobOffer:
    """Oferta de empleo normalizada, independiente del portal de origen."""

    portal: str
    title: str
    company: str
    location: str
    url: str
    external_id: str = ""
    published_at: datetime | None = None
    raw_text: str = ""

    @property
    def fingerprint(self) -> str:
        """Hash estable para deduplicar ofertas entre ejecuciones."""
        key = f"{self.portal}|{self.external_id or self.url}"
        return sha256(key.encode("utf-8")).hexdigest()

    def __post_init__(self) -> None:
        if not self.portal:
            raise ValueError("JobOffer.portal no puede estar vacio")
        if not self.title:
            raise ValueError("JobOffer.title no puede estar vacio")
        if not self.url:
            raise ValueError("JobOffer.url no puede estar vacio")
