"""Repositorio SQLite para ofertas de empleo con deduplicacion."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from job_watcher.models import JobOffer

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    fingerprint   TEXT PRIMARY KEY,
    portal        TEXT NOT NULL,
    title         TEXT NOT NULL,
    company       TEXT NOT NULL,
    location      TEXT NOT NULL,
    url           TEXT NOT NULL,
    external_id   TEXT NOT NULL,
    published_at  TEXT,
    raw_text      TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    notified_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_portal ON jobs(portal);
CREATE INDEX IF NOT EXISTS idx_jobs_notified ON jobs(notified_at);
CREATE TABLE IF NOT EXISTS scrape_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    portal        TEXT NOT NULL,
    scraped_count INTEGER NOT NULL,
    run_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_portal_time ON scrape_runs(portal, run_at);
"""


class JobDatabase:
    """Persistencia local thread-safe de ofertas con dedupe por fingerprint."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._initialize()

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def is_new(self, offer: JobOffer) -> bool:
        """True si la oferta no esta persistida aun."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT 1 FROM jobs WHERE fingerprint = ?",
                (offer.fingerprint,),
            )
            return cur.fetchone() is None

    def save(self, offer: JobOffer) -> None:
        """Inserta o actualiza una oferta. Idempotente."""
        now = datetime.now(UTC).isoformat()
        published = offer.published_at.isoformat() if offer.published_at else None
        with self._write_lock, self._connect() as conn:
            conn.execute(
                """
                    INSERT INTO jobs (fingerprint, portal, title, company, location,
                                      url, external_id, published_at, raw_text, discovered_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fingerprint) DO UPDATE SET
                        title = excluded.title,
                        company = excluded.company,
                        location = excluded.location,
                        url = excluded.url
                    """,
                (
                    offer.fingerprint,
                    offer.portal,
                    offer.title,
                    offer.company,
                    offer.location,
                    offer.url,
                    offer.external_id,
                    published,
                    offer.raw_text,
                    now,
                ),
            )

    def mark_notified(self, offer: JobOffer) -> None:
        """Marca la oferta como notificada al usuario."""
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET notified_at = ? WHERE fingerprint = ?",
                (now, offer.fingerprint),
            )

    def count(self) -> int:
        """Total de ofertas persistidas."""
        with self._connect() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM jobs")
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def log_scrape_run(self, portal: str, count: int) -> None:
        """Registra el numero de ofertas scrapeadas por portal."""
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO scrape_runs (portal, scraped_count, run_at) VALUES (?, ?, ?)",
                (portal, count, now),
            )

    def get_scrape_baseline(self, portal: str, days: int = 7) -> tuple[int, float] | None:
        """Promedio de scraped_count en los ultimos N dias.

        Retorna None si hay menos de 2 runs (no hay suficiente historial).
        """
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT scraped_count FROM scrape_runs WHERE portal = ? AND run_at >= ?",
                (portal, cutoff),
            ).fetchall()
        if len(rows) < 2:
            return None
        counts = [int(r[0]) for r in rows]
        return (len(counts), sum(counts) / len(counts))

    def get_last_scraped(self, portal: str) -> int | None:
        """Ultimo scraped_count registrado para portal, o None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT scraped_count FROM scrape_runs WHERE portal = ? ORDER BY id DESC LIMIT 1",
                (portal,),
            ).fetchone()
        return int(row[0]) if row else None
