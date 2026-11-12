"""Tests de BaseScraper y registry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from job_watcher.models import JobOffer
from job_watcher.scrapers.base import BaseScraper
from job_watcher.scrapers.registry import SCRAPERS, get_scraper


class _FakeScraper(BaseScraper):
    portal = "fake"

    def parse(self, html: str) -> list[JobOffer]:
        if "no-jobs" in html:
            return []
        return [
            JobOffer(
                portal=self.portal,
                title="Fake Job",
                company="ACME",
                location="Porlamar",
                url="https://example.com/1",
                external_id="1",
            )
        ]


def test_base_scraper_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseScraper()  # type: ignore[abstract]


def test_fetch_uses_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.text = "<html>ok</html>"
    mock_response.raise_for_status.return_value = None

    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr("job_watcher.scrapers.base.requests.get", mock_get)

    scraper = _FakeScraper(user_agent="test-ua/1.0")
    html = scraper.fetch("https://example.com")

    assert html == "<html>ok</html>"
    args, kwargs = mock_get.call_args
    assert args[0] == "https://example.com"
    assert kwargs["headers"]["User-Agent"] == "test-ua/1.0"


def test_run_composes_fetch_and_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.text = "<html>jobs here</html>"
    mock_response.raise_for_status.return_value = None
    monkeypatch.setattr(
        "job_watcher.scrapers.base.requests.get",
        MagicMock(return_value=mock_response),
    )

    offers = _FakeScraper().run("https://example.com")
    assert len(offers) == 1
    assert offers[0].title == "Fake Job"


def test_run_returns_empty_when_no_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.text = "no-jobs here"
    mock_response.raise_for_status.return_value = None
    monkeypatch.setattr(
        "job_watcher.scrapers.base.requests.get",
        MagicMock(return_value=mock_response),
    )

    offers = _FakeScraper().run("https://example.com")
    assert offers == []


def test_registry_contains_unmejorempleo() -> None:
    assert "unmejorempleo" in SCRAPERS


def test_get_scraper_unknown_raises() -> None:
    with pytest.raises(KeyError, match="no-existe"):
        get_scraper("no-existe")
