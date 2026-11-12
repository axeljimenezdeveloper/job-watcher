"""Tests del monitor de scrapers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from job_watcher.db import JobDatabase
from job_watcher.monitor import check_and_alert, format_alert, should_alert

# --- should_alert (funcion pura) ---


def test_should_alert_first_drop() -> None:
    assert (
        should_alert(
            current_count=3,
            baseline_avg=68.0,
            last_count=68,
            history_runs=10,
            min_history_runs=5,
        )
        is True
    )


def test_should_alert_no_alert_when_previous_also_low() -> None:
    assert (
        should_alert(
            current_count=3,
            baseline_avg=68.0,
            last_count=3,
            history_runs=10,
            min_history_runs=5,
        )
        is False
    )


def test_should_alert_no_alert_when_healthy() -> None:
    assert (
        should_alert(
            current_count=68,
            baseline_avg=68.0,
            last_count=68,
            history_runs=10,
            min_history_runs=5,
        )
        is False
    )


def test_should_alert_no_alert_when_insufficient_history() -> None:
    assert (
        should_alert(
            current_count=3,
            baseline_avg=68.0,
            last_count=68,
            history_runs=3,
            min_history_runs=5,
        )
        is False
    )


def test_should_alert_respects_threshold() -> None:
    # 68 -> 40 = 41% drop, no supera 50%
    assert (
        should_alert(
            current_count=40,
            baseline_avg=68.0,
            last_count=68,
            history_runs=10,
            min_history_runs=5,
            drop_threshold=0.5,
        )
        is False
    )


def test_should_alert_at_threshold_boundary() -> None:
    # 68 -> 33 = 51.5% drop, si supera 50%
    assert (
        should_alert(
            current_count=33,
            baseline_avg=68.0,
            last_count=68,
            history_runs=10,
            min_history_runs=5,
            drop_threshold=0.5,
        )
        is True
    )


def test_should_alert_handles_none_last() -> None:
    assert (
        should_alert(
            current_count=3,
            baseline_avg=68.0,
            last_count=None,
            history_runs=10,
            min_history_runs=5,
        )
        is True
    )


def test_should_alert_zero_baseline_no_alert() -> None:
    assert (
        should_alert(
            current_count=0,
            baseline_avg=0.0,
            last_count=None,
            history_runs=10,
            min_history_runs=5,
        )
        is False
    )


# --- format_alert ---


def test_format_alert_contains_data() -> None:
    msg = format_alert("computrabajo", 3, 68.0, 10)
    assert "computrabajo" in msg
    assert "3" in msg
    assert "68" in msg
    assert "10" in msg


# --- JobDatabase: scrape_runs methods ---


def test_log_scrape_run_persists(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    db.log_scrape_run("computrabajo", 68)
    assert db.get_last_scraped("computrabajo") == 68


def test_get_last_scraped_none_initially(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    assert db.get_last_scraped("computrabajo") is None


def test_get_scrape_baseline_none_with_one_run(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    db.log_scrape_run("computrabajo", 68)
    assert db.get_scrape_baseline("computrabajo") is None


def test_get_scrape_baseline_computes_avg(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    for c in [60, 68, 70, 65, 72]:
        db.log_scrape_run("computrabajo", c)
    baseline = db.get_scrape_baseline("computrabajo")
    assert baseline is not None
    runs, avg = baseline
    assert runs == 5
    assert abs(avg - 67.0) < 0.01


def test_get_scrape_baseline_isolated_by_portal(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    db.log_scrape_run("computrabajo", 68)
    db.log_scrape_run("computrabajo", 70)
    db.log_scrape_run("trabajo_org", 232)
    db.log_scrape_run("trabajo_org", 230)
    a = db.get_scrape_baseline("computrabajo")
    b = db.get_scrape_baseline("trabajo_org")
    assert a is not None and b is not None
    assert a[1] == 69.0
    assert b[1] == 231.0


# --- check_and_alert (integracion) ---


def test_check_and_alert_sends_on_first_drop(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    for _ in range(6):
        db.log_scrape_run("computrabajo", 68)

    notifier = MagicMock()
    result = check_and_alert("computrabajo", 3, db, notifier)

    assert result is True
    assert notifier.send.call_count == 1
    text = notifier.send.call_args[0][0]
    assert "computrabajo" in text
    assert "3" in text


def test_check_and_alert_no_alert_insufficient_history(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    for _ in range(2):
        db.log_scrape_run("computrabajo", 68)

    notifier = MagicMock()
    result = check_and_alert("computrabajo", 3, db, notifier)

    assert result is False
    assert notifier.send.call_count == 0


def test_check_and_alert_no_alert_if_already_low(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    for _ in range(6):
        db.log_scrape_run("computrabajo", 68)
    db.log_scrape_run("computrabajo", 2)

    notifier = MagicMock()
    result = check_and_alert("computrabajo", 3, db, notifier)

    assert result is False
    assert notifier.send.call_count == 0
