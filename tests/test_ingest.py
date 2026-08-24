"""Phase 2: ingest and normalize."""

import pytest

from pipeline.ingest import canonicalize_url, ingest_all, ingest_feed
from pipeline.models import Feed
from tests.conftest import StubFetcher, fixture_feed

TECH_PRESS = Feed(name="Tech Press Daily", url="https://techpress.example.com/rss")
LAB_BLOG = Feed(name="Frontier Lab Blog", url="https://lab.example.com/feed", source_weight=0.95)
AGGREGATOR = Feed(name="Aggregator Wire", url="https://wire.example.com/rss", source_weight=0.5)


def stub_for(*feeds: tuple[Feed, str], errors: set[str] | None = None) -> StubFetcher:
    return StubFetcher(
        {feed.url: fixture_feed(fixture) for feed, fixture in feeds},
        errors=errors,
    )


def test_happy_path_fields() -> None:
    fetcher = stub_for((TECH_PRESS, "tech_press.xml"))
    articles = ingest_feed(TECH_PRESS, fetcher)

    assert len(articles) == 3
    first = articles[0]
    assert first.title == "OpenAI launches GPT-6 with real-time reasoning"
    assert first.source == "Tech Press Daily"
    assert first.published_at is not None
    assert first.published_at.year == 2026
    assert first.snippet.startswith("OpenAI today announced GPT-6")
    assert first.id  # stable hash assigned


def test_canonical_url_strips_tracking_params() -> None:
    url = "https://a.example.com/story?utm_source=rss&utm_medium=feed&id=7&fbclid=xyz"
    assert canonicalize_url(url) == "https://a.example.com/story?id=7"

    fetcher = stub_for((TECH_PRESS, "tech_press.xml"))
    [gpt6, *_] = ingest_feed(TECH_PRESS, fetcher)
    assert "utm_" not in gpt6.canonical_url
    assert gpt6.url != gpt6.canonical_url  # original preserved for linking


def test_atom_feed_parses() -> None:
    fetcher = stub_for((LAB_BLOG, "lab_blog.xml"))
    articles = ingest_feed(LAB_BLOG, fetcher)
    assert [a.title for a in articles] == [
        "Introducing GPT-6",
        "Scaling sparse attention to 100M context",
    ]
    assert all(a.source_weight == 0.95 for a in articles)


def test_entry_without_link_is_skipped() -> None:
    fetcher = stub_for((AGGREGATOR, "aggregator.xml"))
    articles = ingest_feed(AGGREGATOR, fetcher)
    titles = [a.title for a in articles]
    assert "Untitled item with no link" not in titles
    assert len(articles) == 3


def test_missing_date_is_kept_as_unknown() -> None:
    # Decision (PHASES phase 2): keep the article, mark published_at unknown;
    # the freshness gate treats unknown dates as stale and drops them there.
    feed = Feed(name="No Dates Feed", url="https://nodates.example.com/rss")
    fetcher = stub_for((feed, "no_dates.xml"))
    [article] = ingest_feed(feed, fetcher)
    assert article.published_at is None


def test_malformed_feed_returns_empty_not_raise() -> None:
    feed = Feed(name="Broken", url="https://broken.example.com/rss")
    fetcher = stub_for((feed, "malformed.xml"))
    assert ingest_feed(feed, fetcher) == []


def test_empty_feed_returns_empty() -> None:
    feed = Feed(name="Empty", url="https://empty.example.com/rss")
    fetcher = stub_for((feed, "empty.xml"))
    assert ingest_feed(feed, fetcher) == []


def test_failed_feed_skipped_others_continue() -> None:
    fetcher = stub_for(
        (TECH_PRESS, "tech_press.xml"),
        (LAB_BLOG, "lab_blog.xml"),
        errors={LAB_BLOG.url},
    )
    articles = ingest_all([TECH_PRESS, LAB_BLOG], fetcher)
    assert len(articles) == 3  # tech press only
    assert fetcher.calls == [TECH_PRESS.url, LAB_BLOG.url]


def test_ingest_all_dedupes_exact_canonical_urls() -> None:
    twin = Feed(name="Mirror Feed", url="https://mirror.example.com/rss")
    fetcher = stub_for((TECH_PRESS, "tech_press.xml"), (twin, "tech_press.xml"))
    articles = ingest_all([TECH_PRESS, twin], fetcher)
    assert len(articles) == 3  # second copy collapsed


@pytest.mark.network
def test_live_feeds_reachable() -> None:
    """Manual check only: uv run pytest -m network"""
    from pipeline.config import load_feeds
    from pipeline.http import HttpxFetcher

    articles = ingest_all(load_feeds(), HttpxFetcher())
    assert len(articles) > 0
