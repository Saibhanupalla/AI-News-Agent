"""Ingest: fetch curated RSS feeds and normalize entries into Articles.

A dead feed is skipped with a log line; it must never fail the day.
"""

import hashlib
import logging
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser

from pipeline.http import FeedFetchError, Fetcher
from pipeline.models import Article, Feed

logger = logging.getLogger(__name__)

# Query params that identify tracking, not content.
TRACKING_PREFIXES = ("utm_",)
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "cmpid"}


def canonicalize_url(url: str) -> str:
    """Strip tracking params and fragments so the same story compares equal."""
    scheme, netloc, path, query, _fragment = urlsplit(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if not key.lower().startswith(TRACKING_PREFIXES) and key.lower() not in TRACKING_PARAMS
    ]
    return urlunsplit((scheme, netloc, path.rstrip("/") or path, urlencode(kept), ""))


def article_id(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode()).hexdigest()[:16]


def _parse_published(entry: feedparser.FeedParserDict) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = entry.get(attr)
        if parsed:
            return datetime(*parsed[:6], tzinfo=UTC)
    return None


def normalize_entry(entry: feedparser.FeedParserDict, feed: Feed) -> Article | None:
    title = (entry.get("title") or "").strip()
    url = (entry.get("link") or "").strip()
    if not title or not url:
        return None

    canonical = canonicalize_url(url)
    snippet = (entry.get("summary") or entry.get("description") or "").strip()

    return Article(
        id=article_id(canonical),
        title=title,
        url=url,
        canonical_url=canonical,
        source=feed.name,
        published_at=_parse_published(entry),
        snippet=snippet,
        source_weight=feed.source_weight,
    )


def ingest_feed(feed: Feed, fetcher: Fetcher) -> list[Article]:
    """Fetch and normalize one feed. Returns [] on any failure."""
    try:
        body = fetcher.fetch(feed.url)
    except FeedFetchError as exc:
        logger.warning("skipping feed %s: %s", feed.name, exc)
        return []

    parsed = feedparser.parse(body)
    if parsed.bozo and not parsed.entries:
        logger.warning("skipping feed %s: malformed (%s)", feed.name, parsed.bozo_exception)
        return []

    articles = []
    for entry in parsed.entries:
        article = normalize_entry(entry, feed)
        if article is not None:
            articles.append(article)
    return articles


def ingest_all(feeds: list[Feed], fetcher: Fetcher) -> list[Article]:
    """Ingest every feed, skipping failures. Deduplicates exact canonical URLs."""
    seen: set[str] = set()
    articles: list[Article] = []
    for feed in feeds:
        for article in ingest_feed(feed, fetcher):
            if article.canonical_url in seen:
                continue
            seen.add(article.canonical_url)
            articles.append(article)
    logger.info("ingested %d unique articles from %d feeds", len(articles), len(feeds))
    return articles
