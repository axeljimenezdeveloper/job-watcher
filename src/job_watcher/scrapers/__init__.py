"""Scrapers de portales de empleo."""

from job_watcher.scrapers.base import BaseScraper
from job_watcher.scrapers.registry import SCRAPERS, get_scraper

__all__ = ["SCRAPERS", "BaseScraper", "get_scraper"]
