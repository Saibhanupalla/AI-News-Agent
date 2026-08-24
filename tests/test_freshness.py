"""Phase 4: freshness gate and story memory. The exam: day 2 is not a copy of day 1."""

from datetime import timedelta
from pathlib import Path

from pipeline.cluster import cluster_articles
from pipeline.freshness import apply_freshness
from pipeline.ingest import article_id, canonicalize_url
from pipeline.memory import load_memory, prune_memory, record_shipped, save_memory
from pipeline.models import (
    Article,
    Cluster,
    DropReason,
    FreshnessLabel,
    StoryMemory,
)
from tests.conftest import FROZEN_NOW, FROZEN_TODAY


def make_cluster(
    title: str,
    url: str,
    hours_old: float = 4,
    dated: bool = True,
    max_age_hours: int = 36,
) -> Cluster:
    canonical = canonicalize_url(url)
    published = FROZEN_NOW - timedelta(hours=hours_old) if dated else None
    article = Article(
        id=article_id(canonical),
        title=title,
        url=url,
        canonical_url=canonical,
        source="Fixture Source",
        published_at=published,
        max_age_hours=max_age_hours,
    )
    [cluster] = cluster_articles([article])
    return cluster


def shipped_memory(*clusters: Cluster, summary: str = "Yesterday's summary.") -> StoryMemory:
    for cluster in clusters:
        cluster.summary = summary
    yesterday = "2026-08-23"
    return record_shipped(StoryMemory(), list(clusters), yesterday)


def test_yesterdays_url_is_dropped_as_duplicate() -> None:
    story = make_cluster("OpenAI launches GPT-6", "https://a.example.com/gpt6")
    memory = shipped_memory(make_cluster("OpenAI launches GPT-6", "https://a.example.com/gpt6"))

    kept, dropped = apply_freshness([story], memory, FROZEN_NOW)
    assert kept == []
    assert [(c.title, r) for c, r in dropped] == [
        ("OpenAI launches GPT-6", DropReason.DUPLICATE_URL)
    ]


def test_same_title_new_url_becomes_possible_update() -> None:
    # Chosen rule: similar title with a new URL is NOT silently dropped; it is labeled
    # possible_update, carries yesterday's summary, and the LLM stage decides its fate.
    yesterday = make_cluster("OpenAI launches GPT-6 today", "https://a.example.com/gpt6")
    memory = shipped_memory(yesterday)
    today = make_cluster("OpenAI launches GPT-6 today", "https://b.example.com/openai-gpt6-out")

    [kept], dropped = (lambda r: (r[0], r[1]))(apply_freshness([today], memory, FROZEN_NOW))
    assert dropped == []
    assert kept.freshness == FreshnessLabel.POSSIBLE_UPDATE
    assert kept.previous_summary == "Yesterday's summary."
    assert kept.event_key == yesterday.cluster_id  # inherits the shipped event key


def test_new_story_not_in_memory_is_kept_as_new() -> None:
    memory = shipped_memory(make_cluster("Old story", "https://a.example.com/old"))
    story = make_cluster("Cerebra raises $400M for inference chips", "https://b.example.com/c")

    [kept], dropped = (lambda r: (r[0], r[1]))(apply_freshness([story], memory, FROZEN_NOW))
    assert dropped == []
    assert kept.freshness == FreshnessLabel.NEW


def test_stale_cluster_is_dropped() -> None:
    story = make_cluster("Week-old story", "https://a.example.com/old", hours_old=170)
    kept, dropped = apply_freshness([story], StoryMemory(), FROZEN_NOW)
    assert kept == []
    assert dropped[0][1] == DropReason.STALE


def test_undated_cluster_is_dropped_as_stale() -> None:
    story = make_cluster("Undated story", "https://a.example.com/undated", dated=False)
    kept, dropped = apply_freshness([story], StoryMemory(), FROZEN_NOW)
    assert kept == []
    assert dropped[0][1] == DropReason.STALE


def test_lab_blog_gets_wider_age_window() -> None:
    story = make_cluster(
        "Lab research post",
        "https://lab.example.com/post",
        hours_old=42,
        max_age_hours=48,
    )
    kept, dropped = apply_freshness([story], StoryMemory(), FROZEN_NOW)
    assert len(kept) == 1


def test_memory_prunes_entries_older_than_seven_days() -> None:
    old = make_cluster("Ancient story", "https://a.example.com/ancient")
    recent = make_cluster("Recent story about chips", "https://b.example.com/recent")
    memory = record_shipped(StoryMemory(), [old], "2026-08-16")  # 8 days before today
    memory = record_shipped(memory, [recent], "2026-08-22")

    pruned = prune_memory(memory, FROZEN_TODAY)
    assert [e.title for e in pruned.entries] == ["Recent story about chips"]

    # And a pruned entry no longer blocks a story.
    story = make_cluster("Ancient story", "https://a.example.com/ancient")
    kept, _ = apply_freshness([story], pruned, FROZEN_NOW)
    assert len(kept) == 1


def test_memory_round_trip(data_dir: Path) -> None:
    path = data_dir / "memory" / "recent_stories.json"
    memory = shipped_memory(make_cluster("Round trip story", "https://a.example.com/rt"))
    save_memory(memory, path)

    loaded = load_memory(path)
    assert loaded == memory

    missing = load_memory(data_dir / "memory" / "does_not_exist.json")
    assert missing == StoryMemory()


def test_record_shipped_updates_existing_event() -> None:
    first = make_cluster("Saga day one", "https://a.example.com/saga-1")
    first.summary = "Day one."
    memory = record_shipped(StoryMemory(), [first], "2026-08-22")

    followup = make_cluster("Saga day one continues", "https://a.example.com/saga-2")
    followup.event_key = first.cluster_id
    followup.summary = "Day two development."
    memory = record_shipped(memory, [followup], "2026-08-23")

    assert len(memory.entries) == 1
    entry = memory.entries[0]
    assert entry.last_shipped == "2026-08-23"
    assert entry.last_summary == "Day two development."
    assert "https://a.example.com/saga-1" in entry.urls
    assert "https://a.example.com/saga-2" in entry.urls


def test_two_day_exam_day_two_is_not_a_copy_of_day_one() -> None:
    """PHASES phase 4 gate: run day A, feed the same items back as day B."""
    day_a = [
        make_cluster("OpenAI launches GPT-6", "https://a.example.com/gpt6"),
        make_cluster("EU approves AI liability rules", "https://b.example.com/eu"),
        make_cluster("Cerebra raises $400M", "https://c.example.com/cerebra"),
    ]
    kept_a, dropped_a = apply_freshness(day_a, StoryMemory(), FROZEN_NOW)
    assert len(kept_a) == 3 and dropped_a == []

    memory = record_shipped(StoryMemory(), kept_a, FROZEN_TODAY)

    day_b = [
        make_cluster("OpenAI launches GPT-6", "https://a.example.com/gpt6"),
        make_cluster("EU approves AI liability rules", "https://b.example.com/eu"),
        make_cluster("Cerebra raises $400M", "https://c.example.com/cerebra"),
    ]
    day_b_now = FROZEN_NOW + timedelta(days=1)
    kept_b, dropped_b = apply_freshness(day_b, memory, day_b_now)

    assert kept_b == []  # zero copies of day A ship on day B
    assert {r for _, r in dropped_b} == {DropReason.DUPLICATE_URL}
