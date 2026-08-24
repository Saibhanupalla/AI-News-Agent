"""Phase 1: the harness itself is trustworthy."""

import feedparser
import pytest

from pipeline.http import FeedFetchError
from pipeline.llm import ClusterAnnotation
from pipeline.models import Article, Cluster, StoryType
from tests.conftest import FakeLLM, StubFetcher, default_annotation, fixture_feed


def make_cluster(cluster_id: str = "c1", title: str = "A fixture story") -> Cluster:
    return Cluster(
        cluster_id=cluster_id,
        title=title,
        articles=[
            Article(
                id="a1",
                title=title,
                url="https://example.com/a1",
                canonical_url="https://example.com/a1",
                source="Fixture Source",
            )
        ],
    )


def test_fixture_feeds_parse() -> None:
    for name, expected_items in [
        ("tech_press.xml", 3),
        ("lab_blog.xml", 2),
        ("aggregator.xml", 4),
        ("no_dates.xml", 1),
        ("empty.xml", 0),
    ]:
        parsed = feedparser.parse(fixture_feed(name))
        assert len(parsed.entries) == expected_items, name


def test_malformed_fixture_yields_no_entries() -> None:
    parsed = feedparser.parse(fixture_feed("malformed.xml"))
    assert len(parsed.entries) == 0


def test_stub_fetcher_returns_fixture_bytes_without_network() -> None:
    stub = StubFetcher({"https://feed.example.com/rss": fixture_feed("tech_press.xml")})
    body = stub.fetch("https://feed.example.com/rss")
    assert b"GPT-6" in body
    assert stub.calls == ["https://feed.example.com/rss"]


def test_stub_fetcher_raises_for_planted_error() -> None:
    stub = StubFetcher({}, errors={"https://down.example.com/rss"})
    with pytest.raises(FeedFetchError):
        stub.fetch("https://down.example.com/rss")


def test_fake_llm_records_calls_and_returns_canned_annotation() -> None:
    cluster = make_cluster()
    canned = ClusterAnnotation(
        cluster_id="c1",
        topic_ids=["policy"],
        summary="Canned summary.",
        story_type=StoryType.NEWS,
        novelty=1.0,
        reader_value=0.9,
        event_key="fixture-event",
    )
    fake = FakeLLM(annotations={"c1": canned})
    result = fake.annotate_clusters([cluster])
    assert result == [canned]
    assert fake.annotate_calls == [["c1"]]


def test_fake_llm_falls_back_to_default_annotation() -> None:
    cluster = make_cluster(cluster_id="c2")
    fake = FakeLLM()
    [annotation] = fake.annotate_clusters([cluster])
    assert annotation == default_annotation(cluster)
    assert annotation.story_type == StoryType.NEWS
