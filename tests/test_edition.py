"""Phase 6: LLM refine and edition object (fake LLM only; no live Gemini in CI)."""

import json
from pathlib import Path

import pytest

from pipeline.edition import build_and_write_edition, build_edition
from pipeline.gemini import MissingApiKeyError, load_api_key
from pipeline.llm import ClusterAnnotation, EditorialDecision
from pipeline.memory import load_memory, record_shipped
from pipeline.models import (
    Edition,
    FreshnessLabel,
    StoryMemory,
    StoryType,
)
from tests.conftest import FROZEN_TODAY, FakeLLM
from tests.test_freshness import make_cluster


def annotation(cluster_id: str, **overrides) -> ClusterAnnotation:
    defaults = dict(
        cluster_id=cluster_id,
        topic_ids=["foundation-models"],
        summary="A fixture summary.",
        why_it_matters="Fixture relevance.",
        story_type=StoryType.NEWS,
        novelty=0.9,
        reader_value=0.8,
        event_key=f"event-{cluster_id}",
    )
    defaults.update(overrides)
    return ClusterAnnotation(**defaults)


def build_fixture_world():
    gpt6 = make_cluster("OpenAI launches GPT-6", "https://a.example.com/gpt6")
    policy = make_cluster("EU approves AI liability rules", "https://b.example.com/eu")
    opinion = make_cluster("Why I think AI is overrated", "https://c.example.com/hot-take")
    lowvalue = make_cluster("Minor plugin update for niche tool", "https://d.example.com/minor")
    clusters = [gpt6, policy, opinion, lowvalue]

    fake = FakeLLM(
        annotations={
            gpt6.cluster_id: annotation(gpt6.cluster_id, event_key="openai-gpt6"),
            policy.cluster_id: annotation(
                policy.cluster_id, topic_ids=["policy"], event_key="eu-liability"
            ),
            opinion.cluster_id: annotation(
                opinion.cluster_id, story_type=StoryType.OPINION, event_key="hot-take"
            ),
            lowvalue.cluster_id: annotation(
                lowvalue.cluster_id, topic_ids=["tools"], reader_value=0.2, event_key="minor"
            ),
        },
        decision=EditorialDecision(
            intro="A big launch and a policy milestone lead today.",
            must_know_cluster_ids=[gpt6.cluster_id, policy.cluster_id],
            section_order=["foundation-models", "policy", "tools"],
        ),
    )
    return clusters, fake, gpt6, policy


def test_edition_ships_only_news_and_update_above_cutoff() -> None:
    clusters, fake, gpt6, policy = build_fixture_world()
    edition, _ = build_edition(clusters, StoryMemory(), FROZEN_TODAY, fake)

    shipped_ids = {i.cluster_id for i in edition.must_know} | {
        i.cluster_id for items in edition.sections.values() for i in items
    } | {i.cluster_id for i in edition.continuing}

    assert gpt6.cluster_id in shipped_ids
    assert policy.cluster_id in shipped_ids
    assert len(shipped_ids) == 2  # opinion and low-value dropped


def test_edition_schema_is_complete() -> None:
    clusters, fake, *_ = build_fixture_world()
    edition, _ = build_edition(clusters, StoryMemory(), FROZEN_TODAY, fake)

    assert edition.date == FROZEN_TODAY
    assert edition.intro
    assert edition.must_know
    for item in edition.must_know:
        assert item.title and item.summary
        assert item.topic_ids
        assert item.sources and all(s["url"].startswith("https://") for s in item.sources)


def test_possible_update_with_no_new_fact_is_dropped() -> None:
    saga = make_cluster("Chip export saga continues", "https://a.example.com/saga-day2")
    saga.freshness = FreshnessLabel.POSSIBLE_UPDATE
    saga.previous_summary = "Exports were restricted yesterday."
    fake = FakeLLM(
        annotations={saga.cluster_id: annotation(saga.cluster_id, update_delta="")}
    )
    edition, _ = build_edition([saga], StoryMemory(), FROZEN_TODAY, fake)
    assert edition.must_know == []
    assert edition.sections == {}
    assert edition.continuing == []


def test_possible_update_with_new_fact_ships_as_continuing_not_must_know() -> None:
    saga = make_cluster("Chip export saga continues", "https://a.example.com/saga-day2")
    saga.freshness = FreshnessLabel.POSSIBLE_UPDATE
    saga.previous_summary = "Exports were restricted yesterday."
    fresh = make_cluster("Unrelated fresh launch", "https://b.example.com/launch")

    fake = FakeLLM(
        annotations={
            saga.cluster_id: annotation(
                saga.cluster_id,
                update_delta="Regulator added GPUs to the restricted list.",
                novelty=0.5,
                event_key="chip-saga",
            ),
            fresh.cluster_id: annotation(fresh.cluster_id, event_key="fresh-launch"),
        },
        decision=EditorialDecision(
            intro="Fixture intro for the day.",
            must_know_cluster_ids=[saga.cluster_id, fresh.cluster_id],
            section_order=["foundation-models"],
        ),
    )
    # The saga already headlined yesterday.
    memory = StoryMemory()
    yesterday_cluster = make_cluster("Chip export saga begins", "https://a.example.com/saga-day1")
    yesterday_cluster.event_key = "chip-saga"
    yesterday_cluster.summary = "Exports were restricted yesterday."
    memory = record_shipped(
        memory, [yesterday_cluster], "2026-08-23", {yesterday_cluster.cluster_id}
    )

    edition, _ = build_edition([saga, fresh], memory, FROZEN_TODAY, fake)

    must_know_ids = {i.cluster_id for i in edition.must_know}
    assert saga.cluster_id not in must_know_ids  # repeat headline blocked (novelty 0.5 < 0.8)
    assert fresh.cluster_id in must_know_ids
    continuing_ids = {i.cluster_id for i in edition.continuing}
    assert saga.cluster_id in continuing_ids
    [saga_item] = edition.continuing
    assert saga_item.story_type == StoryType.UPDATE
    assert saga_item.update_delta


def test_memory_records_shipped_clusters_and_must_know_flag() -> None:
    clusters, fake, gpt6, _ = build_fixture_world()
    _, memory = build_edition(clusters, StoryMemory(), FROZEN_TODAY, fake)

    keys = {e.event_key for e in memory.entries}
    assert keys == {"openai-gpt6", "eu-liability"}
    gpt6_entry = next(e for e in memory.entries if e.event_key == "openai-gpt6")
    assert gpt6_entry.was_must_know
    assert gpt6_entry.last_shipped == FROZEN_TODAY


def test_build_and_write_edition_writes_valid_json(data_dir: Path) -> None:
    clusters, fake, *_ = build_fixture_world()
    out = build_and_write_edition(
        clusters,
        StoryMemory(),
        FROZEN_TODAY,
        llm=fake,
        editions_dir=data_dir / "editions",
        memory_path=data_dir / "memory" / "recent_stories.json",
    )
    assert out.name == f"{FROZEN_TODAY}.json"
    edition = Edition.model_validate(json.loads(out.read_text()))
    assert edition.date == FROZEN_TODAY
    assert load_memory(data_dir / "memory" / "recent_stories.json").entries


def test_llm_calls_are_batched_not_per_article() -> None:
    clusters, fake, *_ = build_fixture_world()
    build_edition(clusters, StoryMemory(), FROZEN_TODAY, fake)
    assert len(fake.annotate_calls) == 1  # one batch for all clusters
    assert len(fake.editorial_calls) == 1


def test_missing_api_key_fails_clearly(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError, match="GEMINI_API_KEY"):
        load_api_key(env_file=tmp_path / "no-env-here")


def test_api_key_loaded_from_env_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=test-key-123\n")
    assert load_api_key(env_file=env_file) == "test-key-123"


@pytest.mark.llm
def test_live_gemini_annotation() -> None:
    """Manual check only: uv run pytest -m llm (needs GEMINI_API_KEY)."""
    import os

    from pipeline.config import REPO_ROOT
    from pipeline.gemini import GeminiClient
    if not os.environ.get("GEMINI_API_KEY") and not (REPO_ROOT / ".env").exists():
        pytest.skip("no key available")

    cluster = make_cluster(
        "OpenAI launches GPT-6 with real-time reasoning",
        "https://techpress.example.com/gpt6",
    )
    client = GeminiClient()
    [result] = client.annotate_clusters([cluster])
    assert result.cluster_id == cluster.cluster_id
    assert result.topic_ids
