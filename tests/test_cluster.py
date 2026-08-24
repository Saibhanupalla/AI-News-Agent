"""Phase 3: same-day dedupe and clustering."""

from pipeline.cluster import cluster_articles, titles_match
from pipeline.ingest import article_id, canonicalize_url, ingest_all
from pipeline.models import Article, Feed
from tests.conftest import StubFetcher, fixture_feed


def article(title: str, url: str, source: str = "Fixture", weight: float = 0.5) -> Article:
    canonical = canonicalize_url(url)
    return Article(
        id=article_id(canonical),
        title=title,
        url=url,
        canonical_url=canonical,
        source=source,
        source_weight=weight,
    )


def test_same_url_twice_is_one_cluster() -> None:
    a = article("OpenAI launches GPT-6", "https://a.example.com/gpt6", source="Outlet A")
    b = article("OpenAI launches GPT-6", "https://a.example.com/gpt6", source="Outlet B")
    clusters = cluster_articles([a, b])
    assert len(clusters) == 1
    assert sorted(clusters[0].sources) == ["Outlet A", "Outlet B"]


def test_same_story_different_urls_similar_titles_is_one_cluster() -> None:
    a = article(
        "OpenAI launches GPT-6 with real-time reasoning",
        "https://techpress.example.com/gpt6-launch",
        source="Tech Press Daily",
    )
    b = article(
        "OpenAI unveils GPT-6, promises real-time reasoning",
        "https://wire.example.com/openai-gpt6",
        source="Aggregator Wire",
    )
    clusters = cluster_articles([a, b])
    assert len(clusters) == 1
    assert len(clusters[0].urls) == 2


def test_unrelated_titles_stay_separate() -> None:
    a = article("OpenAI launches GPT-6", "https://a.example.com/gpt6")
    b = article("EU approves AI liability rules", "https://b.example.com/eu-rules")
    assert len(cluster_articles([a, b])) == 2


def test_launch_and_pricing_rumor_do_not_merge() -> None:
    assert not titles_match("Gemini 3 launch", "Gemini 3 pricing rumor")


def test_tracking_param_urls_collapse() -> None:
    a = article("Cerebra raises $400M", "https://wire.example.com/cerebra?utm_source=rss")
    b = article("Cerebra raises $400M", "https://wire.example.com/cerebra?fbclid=zzz")
    clusters = cluster_articles([a, b])
    assert len(clusters) == 1


def test_cluster_ids_are_stable() -> None:
    a = article("Story one", "https://a.example.com/1")
    b = article("Story two about something else", "https://b.example.com/2")
    first = {c.cluster_id for c in cluster_articles([a, b])}
    second = {c.cluster_id for c in cluster_articles([a, b])}
    assert first == second


def test_cluster_title_comes_from_highest_weight_source() -> None:
    a = article("OpenAI unveils GPT-6, promises real-time reasoning", "https://w.example.com/1")
    b = article(
        "OpenAI launches GPT-6 with real-time reasoning",
        "https://lab.example.com/gpt6",
        source="Frontier Lab Blog",
        weight=0.95,
    )
    [cluster] = cluster_articles([a, b])
    assert cluster.title == b.title


def test_terse_lab_title_stays_separate_from_press_coverage() -> None:
    # Known v1 limitation: "Introducing GPT-6" scores ~45 vs press headlines, far below
    # the merge threshold. Lowering the threshold enough to merge it would also merge
    # "launch" with "pricing rumor" (~70). The lab post ships as its own cluster.
    a = article("OpenAI launches GPT-6 with real-time reasoning", "https://p.example.com/gpt6")
    b = article("Introducing GPT-6", "https://lab.example.com/gpt6", source="Frontier Lab Blog")
    assert len(cluster_articles([a, b])) == 2


def test_fixture_pack_collapses_to_known_count() -> None:
    feeds = [
        Feed(name="Tech Press Daily", url="https://techpress.example.com/rss", source_weight=0.8),
        Feed(name="Frontier Lab Blog", url="https://lab.example.com/feed", source_weight=0.95),
        Feed(name="Aggregator Wire", url="https://wire.example.com/rss", source_weight=0.5),
    ]
    fetcher = StubFetcher(
        {
            feeds[0].url: fixture_feed("tech_press.xml"),
            feeds[1].url: fixture_feed("lab_blog.xml"),
            feeds[2].url: fixture_feed("aggregator.xml"),
        }
    )
    articles = ingest_all(feeds, fetcher)
    clusters = cluster_articles(articles)

    # 8 articles in. The two reworded press GPT-6 headlines merge; the terse lab post
    # ("Introducing GPT-6") stays its own cluster (see limitation test above).
    press_gpt6 = [c for c in clusters if "GPT-6" in c.title and len(c.articles) == 2]
    assert len(press_gpt6) == 1
    assert sorted(press_gpt6[0].sources) == ["Aggregator Wire", "Tech Press Daily"]
    assert len(clusters) == 7

    for cluster in clusters:
        assert cluster.sources
        assert cluster.urls
