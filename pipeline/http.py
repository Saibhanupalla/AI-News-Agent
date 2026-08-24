"""HTTP seam: ingest depends on this protocol, tests inject a stub."""

from typing import Protocol

import httpx


class FeedFetchError(Exception):
    """A single feed failed to fetch. Callers skip the feed, never the day."""


class Fetcher(Protocol):
    def fetch(self, url: str) -> bytes:
        """Return raw feed bytes or raise FeedFetchError."""
        ...


class HttpxFetcher:
    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self._timeout = timeout_seconds

    def fetch(self, url: str) -> bytes:
        try:
            response = httpx.get(
                url,
                timeout=self._timeout,
                follow_redirects=True,
                headers={"User-Agent": "ai-news-agent/0.1 (+daily briefing bot)"},
            )
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as exc:
            raise FeedFetchError(f"{url}: {exc}") from exc
