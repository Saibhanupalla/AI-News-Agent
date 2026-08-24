"""Phase 5: quality and relevance gate."""

from pipeline.cluster import cluster_articles
from pipeline.ingest import article_id, canonicalize_url
from pipeline.models import Article, Cluster, DropReason
from pipeline.quality import FeedHealth, apply_quality, tag_topics


def make_cluster(
    title: str,
    *sources: tuple[str, float],
    snippet: str = "",
    url_base: str = "https://example.com",
) -> Cluster:
    articles = []
    for index, (source, weight) in enumerate(sources or [("Fixture", 0.8)]):
        slug = title.lower().replace(" ", "-")[:40]
        url = f"{url_base}/{source.lower().replace(' ', '-')}/{slug}-{index}"
        canonical = canonicalize_url(url)
        articles.append(
            Article(
                id=article_id(canonical),
                title=title,
                url=url,
                canonical_url=canonical,
                source=source,
                snippet=snippet,
                source_weight=weight,
            )
        )
    groups = cluster_articles(articles)
    assert len(groups) == 1
    return groups[0]


def test_listicle_title_dropped_as_evergreen() -> None:
    cluster = make_cluster("The 10 best AI tools to try this weekend")
    kept, dropped = apply_quality([cluster])
    assert kept == []
    assert dropped[0][1] == DropReason.EVERGREEN


def test_weekly_recap_dropped_as_evergreen() -> None:
    cluster = make_cluster("This week in AI: everything you missed")
    _, dropped = apply_quality([cluster])
    assert dropped[0][1] == DropReason.EVERGREEN


def test_off_taxonomy_story_dropped() -> None:
    cluster = make_cluster(
        "Local football club wins championship final",
        ("Sports Wire", 0.8),
        snippet="A thrilling penalty shootout decided the title.",
    )
    _, dropped = apply_quality([cluster])
    assert dropped[0][1] == DropReason.OFF_TOPIC


def test_single_source_vendor_post_below_weight_dropped() -> None:
    cluster = make_cluster(
        "Acme announces revolutionary AI-powered toaster platform",
        ("Acme Vendor Blog", 0.4),
        snippet="Acme's new AI model brings intelligence to breakfast.",
    )
    kept, dropped = apply_quality([cluster])
    assert kept == []
    assert dropped[0][1] == DropReason.LOW_QUALITY


def test_two_independent_sources_kept_and_scored_higher() -> None:
    single = make_cluster(
        "Cerebra raises $400M for wafer-scale inference chips",
        ("Aggregator Wire", 0.6),
        snippet="The startup closed a $400M round for its AI chips.",
    )
    multi = make_cluster(
        "Cerebra raises $400M for wafer-scale inference chips",
        ("Aggregator Wire", 0.6),
        ("Tech Press Daily", 0.8),
        snippet="The startup closed a $400M round for its AI chips.",
    )
    kept, _ = apply_quality([single, multi])
    assert len(kept) == 2
    scores = {len(c.sources): c.quality_score for c in kept}
    assert scores[2] > scores[1]


def test_high_weight_lab_blog_kept() -> None:
    cluster = make_cluster(
        "Introducing GPT-6",
        ("Frontier Lab Blog", 0.95),
        snippet="We are releasing GPT-6, our most capable AI model.",
    )
    kept, dropped = apply_quality([cluster])
    assert dropped == []
    assert kept[0].quality_score == 0.95
    assert "foundation-models" in kept[0].topic_ids


def test_topic_tagging_maps_to_locked_taxonomy() -> None:
    policy = make_cluster(
        "EU parliament approves final AI liability rules",
        ("Tech Press Daily", 0.8),
        snippet="Lawmakers approved liability regulation for high-risk AI.",
    )
    assert "policy" in tag_topics(policy)

    funding = make_cluster(
        "Cerebra raises $400M for AI chips",
        ("Tech Press Daily", 0.8),
        snippet="The startup closed a funding round.",
    )
    tags = tag_topics(funding)
    assert "startups-funding" in tags
    assert "hardware" in tags


def test_feed_health_counters_increment() -> None:
    health = FeedHealth()
    listicle = make_cluster("Top 5 AI apps ranked", ("SEO Farm", 0.3))
    offtopic = make_cluster("Celebrity wedding of the year", ("SEO Farm", 0.3))
    apply_quality([listicle, offtopic], health=health)

    counts = health.as_dict()["SEO Farm"]
    assert counts["evergreen"] == 1
    assert counts["off_topic"] == 1


def test_cap_limits_to_fifteen_clusters() -> None:
    clusters = [
        make_cluster(
            f"AI model release number {i} announced by lab",
            (f"Source {i}", 0.7),
            snippet="A new AI model was released with better benchmarks.",
        )
        for i in range(20)
    ]
    kept, dropped = apply_quality(clusters)
    assert len(kept) == 15
    overflow = [r for _, r in dropped if r == DropReason.LOW_QUALITY]
    assert len(overflow) == 5
