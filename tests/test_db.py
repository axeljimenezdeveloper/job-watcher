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


def test_log_summary_sent_persists(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    db.log_summary_sent()
    assert db.was_summary_sent_since(hours=1) is True


def test_was_summary_sent_since_none_initially(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    assert db.was_summary_sent_since(hours=20) is False


def test_was_summary_sent_since_false_after_window(tmp_path: Path) -> None:
    import sqlite3
    from datetime import UTC, datetime, timedelta

    db = JobDatabase(tmp_path / "jobs.db")
    # Insertar manualmente un resumen viejo (25h atras)
    old = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    with sqlite3.connect(tmp_path / "jobs.db") as conn:
        conn.execute("INSERT INTO summary_log (sent_at) VALUES (?)", (old,))
    assert db.was_summary_sent_since(hours=20) is False


def test_was_summary_sent_since_true_recent(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    db.log_summary_sent()
    assert db.was_summary_sent_since(hours=20) is True


def test_find_recent_duplicate_same_title_company(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    offer = _offer(external_id="1", title="Asistente Admin", company="ACME")
    db.save(offer)
    db.mark_notified(offer)
    assert db.find_recent_duplicate("Asistente Admin", "ACME") is True


def test_find_recent_duplicate_case_insensitive(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    offer = _offer(external_id="1", title="Asistente Admin", company="ACME")
    db.save(offer)
    db.mark_notified(offer)
    assert db.find_recent_duplicate("ASISTENTE ADMIN", "acme") is True


def test_find_recent_duplicate_different_title(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    offer = _offer(external_id="1", title="Asistente Admin", company="ACME")
    db.save(offer)
    db.mark_notified(offer)
    assert db.find_recent_duplicate("Contador", "ACME") is False


def test_find_recent_duplicate_empty_company_returns_false(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    offer = _offer(external_id="1", title="Asistente Admin", company="ACME")
    db.save(offer)
    db.mark_notified(offer)
    assert db.find_recent_duplicate("Asistente Admin", "") is False


def test_find_recent_duplicate_not_notified_returns_false(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    offer = _offer(external_id="1", title="Asistente Admin", company="ACME")
    db.save(offer)  # guardada pero NO notificada
    assert db.find_recent_duplicate("Asistente Admin", "ACME") is False


# --- normalize_for_dedup ---


def test_normalize_for_dedup_strips_parenthesis() -> None:
    from job_watcher.db import normalize_for_dedup

    assert normalize_for_dedup("Asistente Administrativo(a)") == "asistente administrativo"
    assert normalize_for_dedup("Asesor(es)") == "asesor"


def test_normalize_for_dedup_strips_legal_suffixes() -> None:
    from job_watcher.db import normalize_for_dedup

    assert normalize_for_dedup("SERVICIOS DEL FRIO S.A.") == "servicios del frio"
    assert normalize_for_dedup("ACME C.A.") == "acme"
    assert normalize_for_dedup("Empresa SRL") == "empresa"
    assert normalize_for_dedup("Corp LLC") == "corp"


def test_normalize_for_dedup_removes_accents_and_case() -> None:
    from job_watcher.db import normalize_for_dedup

    assert normalize_for_dedup("MECANICO") == "mecanico"
    assert normalize_for_dedup("Gestion de Inventarios") == "gestion de inventarios"
    assert normalize_for_dedup("Mecanico") == "mecanico"


# --- find_recent_duplicate con normalizacion ---


def test_find_recent_duplicate_handles_paren_suffix(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    offer = _offer(
        external_id="1",
        title="Asistente Administrativo(a)",
        company="ACME",
    )
    db.save(offer)
    db.mark_notified(offer)
    assert db.find_recent_duplicate("Asistente Administrativo", "ACME") is True


def test_find_recent_duplicate_handles_legal_suffix(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    offer = _offer(
        external_id="1",
        title="Asistente Admin",
        company="ACME S.A.",
    )
    db.save(offer)
    db.mark_notified(offer)
    assert db.find_recent_duplicate("Asistente Admin", "ACME") is True


def test_find_recent_duplicate_skips_confidencial(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    offer = _offer(external_id="1", title="Asistente Admin", company="CONFIDENCIAL")
    db.save(offer)
    db.mark_notified(offer)
    assert db.find_recent_duplicate("Asistente Admin", "CONFIDENCIAL") is False


# --- migracion ---


def test_migrate_adds_columns_to_existing_db(tmp_path: Path) -> None:
    import sqlite3
    from datetime import UTC, datetime

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE jobs (fingerprint TEXT PRIMARY KEY, portal TEXT, "
            "title TEXT, company TEXT, location TEXT, url TEXT, external_id TEXT, "
            "published_at TEXT, raw_text TEXT, discovered_at TEXT, notified_at TEXT)"
        )
        conn.execute(
            "INSERT INTO jobs (fingerprint, portal, title, company, location, "
            "url, external_id, published_at, raw_text, discovered_at, notified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "fp1",
                "p",
                "Asistente Administrativo(a)",
                "ACME S.A.",
                "l",
                "u",
                "e",
                None,
                "",
                datetime.now(UTC).isoformat(),
                None,
            ),
        )

    JobDatabase(path)  # dispara migracion

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT title_normalized, company_normalized FROM jobs WHERE fingerprint = ?",
            ("fp1",),
        ).fetchone()
    assert row["title_normalized"] == "asistente administrativo"
    assert row["company_normalized"] == "acme"


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "jobs.db"
    JobDatabase(path)
    JobDatabase(path)  # no debe lanzar
