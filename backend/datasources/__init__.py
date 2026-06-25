"""Data source scrapers — all inherit BaseDataSource."""

from backend.datasources.base import BaseDataSource
from backend.datasources.github import GitHubScraper
from backend.datasources.holehe import HoleheScraper
from backend.datasources.maigret import MaigretScraper
from backend.datasources.mock_maigret import MockMaigretScraper

__all__ = [
    "BaseDataSource",
    "GitHubScraper",
    "HoleheScraper",
    "MaigretScraper",
    "MockMaigretScraper",
]
