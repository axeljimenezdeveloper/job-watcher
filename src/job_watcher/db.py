"""Repositorio SQLite para ofertas de empleo con deduplicacion."""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from loguru import logger

from job_watcher.filters import normalize
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
CREATE TABLE IF NOT EXISTS summary_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_summary_log_sent_at ON summary_log(sent_at);
"""

_PAREN_SUFFIX = re.compile(r"\([a-z]{1,2}\)", re.IGNORECASE)
_LEGAL_SUFFIXES = re.compile(
    r"\b(s\.?\s*a\.?\s*s?|c\.?\s*a\.?|srl|llc)\.?(?![a-zA-Z])",
    re.IGNORECASE,
)


def normalize_for_dedup(text: str) -> str:
    """Normaliza para comparar duplicados cross-portal.

    - Quita sufijos parenteticos: "(a)", "(o)", "(os)", "(as)"
    - Quita sufijos legales: "S.A.", "C.A.", "SRL", "LLC"
    - Lowercase, sin tildes, espacios colapsados
    """
    text = _PAREN_SUFFIX.sub("", text)
    text = _LEGAL_SUFFIXES.sub("", text)
    return normalize(text)


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
            self._migrate(conn)
            self._prune(conn)

    @staticmethod
    def _prune(conn: sqlite3.Connection, days: int = 90) -> None:
        """Borra ofertas mas antiguas que N dias para evitar crecimiento indefinido."""
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        cur = conn.execute(
            "DELETE FROM jobs WHERE discovered_at < ?",
            (cutoff,),
        )
        if cur.rowcount > 0:
            logger.info(
                "[db] podadas {} ofertas con mas de {} dias",
                cur.rowcount,
                days,
            )

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Anade columnas *_normalized si faltan. Idempotente."""
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "title_normalized" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN title_normalized TEXT")
        if "company_normalized" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN company_normalized TEXT")
        pending = conn.execute(
            "SELECT fingerprint, title, company FROM jobs "
            "WHERE title_normalized IS NULL OR company_normalized IS NULL"
        ).fetchall()
        for row in pending:
            conn.execute(
                "UPDATE jobs SET title_normalized = ?, company_normalized = ? "
                "WHERE fingerprint = ?",
                (
                    normalize_for_dedup(row["title"]),
                    normalize_for_dedup(row["company"]),
                    row["fingerprint"],
                ),
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_title_norm ON jobs(title_normalized)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company_norm ON jobs(company_normalized)")

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
        title_norm = normalize_for_dedup(offer.title)
        company_norm = normalize_for_dedup(offer.company)
        with self._write_lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (fingerprint, portal, title, company, location,
                                  url, external_id, published_at, raw_text,
                                  discovered_at, title_normalized, company_normalized)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    title = excluded.title,
                    company = excluded.company,
                    location = excluded.location,
                    url = excluded.url,
                    title_normalized = excluded.title_normalized,
                    company_normalized = excluded.company_normalized
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
                    title_norm,
                    company_norm,
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
        """Promedio de scraped_count en los ultimos N dias."""
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

    def log_summary_sent(self) -> None:
        """Registra que se envio un resumen diario."""
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO summary_log (sent_at) VALUES (?)",
                (now,),
            )

    def was_summary_sent_since(self, hours: int) -> bool:
        """True si se envio un resumen en las ultimas N horas."""
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM summary_log WHERE sent_at >= ? LIMIT 1",
                (cutoff,),
            ).fetchone()
        return row is not None

    def find_recent_duplicate(self, title: str, company: str, days: int = 30) -> bool:
        """True si hay una oferta notificada similar en los ultimos N dias.

        Normaliza title y company (quita "(a)", "S.A.", tildes, mayusculas).
        Si company normalizada esta vacia o es "confidencial", retorna False
        (no deduplicar ofertas genericas: preferimos duplicar a perder).
        """
        title_norm = normalize_for_dedup(title)
        company_norm = normalize_for_dedup(company)
        if not company_norm or company_norm == "confidencial":
            return False
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT 1 FROM jobs WHERE "
                "title_normalized = ? AND company_normalized = ? "
                "AND notified_at IS NOT NULL AND notified_at >= ? "
                "LIMIT 1",
                (title_norm, company_norm, cutoff),
            )
            return cur.fetchone() is not None
