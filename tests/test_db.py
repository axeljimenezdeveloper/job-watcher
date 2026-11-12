"""Tests del repositorio SQLite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from job_watcher.db import JobDatabase
from job_watcher.models import JobOffer


def _offer(**overrides: object) -> JobOffer:
    defaults: dict[str, object] = {
        "portal": "unmejorempleo",
        "title": "Analista de Inventarios",
        "company": "ACME",
        "location": "Porlamar, Nueva Esparta",
        "url": "https://example.com/oferta/1",
        "external_id": "abc123",
    }
    defaults.update(overrides)
    return JobOffer(**defaults)  # type: ignore[arg-type]


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[JobDatabase]:
    database = JobDatabase(tmp_path / "jobs.db")
    yield database


def test_new_offer_is_new(db: JobDatabase) -> None:
    assert db.is_new(_offer()) is True


def test_saved_offer_is_not_new(db: JobDatabase) -> None:
    offer = _offer()
    db.save(offer)
    assert db.is_new(offer) is False


def test_save_is_idempotent(db: JobDatabase) -> None:
    offer = _offer()
    db.save(offer)
    db.save(offer)
    assert db.count() == 1


def test_count_reflects_saves(db: JobDatabase) -> None:
    assert db.count() == 0
    db.save(_offer(external_id="a"))
    db.save(_offer(external_id="b"))
    assert db.count() == 2


def test_mark_notified_persists(db: JobDatabase) -> None:
    offer = _offer()
    db.save(offer)
    db.mark_notified(offer)
    assert db.is_new(offer) is False


def test_different_portal_same_id_is_distinct(db: JobDatabase) -> None:
    a = _offer(portal="unmejorempleo", external_id="same")
    b = _offer(portal="trabajo_org", external_id="same")
    db.save(a)
    assert db.is_new(b) is True


def test_db_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "jobs.db"
    first = JobDatabase(path)
    offer = _offer()
    first.save(offer)

    second = JobDatabase(path)
    assert second.is_new(offer) is False
    assert second.count() == 1


def test_concurrent_saves_are_safe(tmp_path: Path) -> None:
    """10 threads guardando ofertas simultaneamente: sin perdida, sin race."""
    import threading

    db = JobDatabase(tmp_path / "jobs.db")
    offers = [_offer(external_id=str(i)) for i in range(10)]
    threads = [threading.Thread(target=db.save, args=(offer,)) for offer in offers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert db.count() == 10


def test_concurrent_log_scrape_runs(tmp_path: Path) -> None:
    """5 threads loggeando scrape_runs: los 5 quedan persistidos."""
    import threading

    db = JobDatabase(tmp_path / "jobs.db")
    threads = [
        threading.Thread(target=db.log_scrape_run, args=(f"portal_{i}", i)) for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for i in range(5):
        assert db.get_last_scraped(f"portal_{i}") == i
