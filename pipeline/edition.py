"""Build the daily edition: apply LLM judgments, enforce editorial rules, write JSON."""

import logging
from pathlib import Path

from pipeline.config import EDITIONS_DIR, MEMORY_PATH
from pipeline.llm import LLMClient
from pipeline.memory import record_shipped, save_memory
from pipeline.models import (
    TOPIC_IDS,
    Cluster,
    DropReason,
    Edition,
    EditionItem,
    FreshnessLabel,
    StoryMemory,
    StoryType,
)

logger = logging.getLogger(__name__)

READER_VALUE_CUTOFF = 0.55
# A repeat must-know needs at least this novelty to headline again.
MAJOR_UPDATE_NOVELTY = 0.8
MUST_KNOW_COUNT = 3


def apply_annotations(
    clusters: list[Cluster],
    llm: LLMClient,
) -> tuple[list[Cluster], list[tuple[Cluster, DropReason]]]:
    """Run the batched annotation call and enforce ship/drop rules."""
    annotations = {a.cluster_id: a for a in llm.annotate_clusters(clusters)}
    kept: list[Cluster] = []
    dropped: list[tuple[Cluster, DropReason]] = []

    for cluster in clusters:
        annotation = annotations.get(cluster.cluster_id)
        if annotation is None:
            dropped.append((cluster, DropReason.LOW_QUALITY))
            continue

        cluster.topic_ids = [t for t in annotation.topic_ids if t in TOPIC_IDS] or (
            cluster.topic_ids
        )
        cluster.summary = annotation.summary
        cluster.why_it_matters = annotation.why_it_matters
        cluster.story_type = annotation.story_type
        cluster.novelty = annotation.novelty
        cluster.reader_value = annotation.reader_value
        cluster.event_key = annotation.event_key or cluster.event_key or cluster.cluster_id
        cluster.update_delta = annotation.update_delta

        if cluster.freshness == FreshnessLabel.POSSIBLE_UPDATE:
            if not cluster.update_delta.strip():
                dropped.append((cluster, DropReason.NO_NEW_FACT))
                continue
            cluster.story_type = StoryType.UPDATE

        if cluster.story_type not in (StoryType.NEWS, StoryType.UPDATE):
            dropped.append((cluster, DropReason.EVERGREEN))
            continue
        if cluster.reader_value is None or cluster.reader_value < READER_VALUE_CUTOFF:
            dropped.append((cluster, DropReason.LOW_READER_VALUE))
            continue

        kept.append(cluster)

    for cluster, reason in dropped:
        logger.info("llm drop [%s]: %s", reason.value, cluster.title)
    return kept, dropped


def to_item(cluster: Cluster) -> EditionItem:
    return EditionItem(
        cluster_id=cluster.cluster_id,
        title=cluster.title,
        summary=cluster.summary,
        why_it_matters=cluster.why_it_matters,
        topic_ids=cluster.topic_ids,
        story_type=cluster.story_type or StoryType.NEWS,
        update_delta=cluster.update_delta,
        sources=[
            {"name": article.source, "url": article.canonical_url}
            for article in cluster.articles
        ],
    )


def pick_must_know(
    ordered_ids: list[str],
    clusters: list[Cluster],
    memory: StoryMemory,
) -> list[Cluster]:
    """Editorial picks, minus anything that already headlined (unless a major update)."""
    was_must_know = {e.event_key for e in memory.entries if e.was_must_know}
    by_id = {c.cluster_id: c for c in clusters}

    picked: list[Cluster] = []
    candidates = [by_id[i] for i in ordered_ids if i in by_id]
    candidates += [c for c in clusters if c not in candidates]  # editorial miss fallback

    for cluster in candidates:
        if len(picked) >= MUST_KNOW_COUNT:
            break
        if cluster.event_key in was_must_know:
            is_major_update = (
                cluster.story_type == StoryType.UPDATE
                and (cluster.novelty or 0) >= MAJOR_UPDATE_NOVELTY
            )
            if not is_major_update:
                continue
        picked.append(cluster)
    return picked


def build_edition(
    clusters: list[Cluster],
    memory: StoryMemory,
    date: str,
    llm: LLMClient,
) -> tuple[Edition, StoryMemory]:
    kept, _dropped = apply_annotations(clusters, llm)

    if not kept:
        edition = Edition(
            date=date, intro="No qualifying stories today.", must_know=[], sections={},
            continuing=[],
        )
        return edition, memory

    decision = llm.editorial(kept)
    must_know_clusters = pick_must_know(decision.must_know_cluster_ids, kept, memory)
    must_know_ids = {c.cluster_id for c in must_know_clusters}

    continuing = [
        c for c in kept if c.story_type == StoryType.UPDATE and c.cluster_id not in must_know_ids
    ]
    continuing_ids = {c.cluster_id for c in continuing}

    section_order = [t for t in decision.section_order if t in TOPIC_IDS] or TOPIC_IDS
    sections: dict[str, list[EditionItem]] = {}
    for cluster in kept:
        if cluster.cluster_id in must_know_ids or cluster.cluster_id in continuing_ids:
            continue
        primary_topic = next(
            (t for t in section_order if t in cluster.topic_ids),
            cluster.topic_ids[0] if cluster.topic_ids else "tools",
        )
        sections.setdefault(primary_topic, []).append(to_item(cluster))

    ordered_sections = {t: sections[t] for t in section_order if t in sections}

    edition = Edition(
        date=date,
        intro=decision.intro,
        must_know=[to_item(c) for c in must_know_clusters],
        sections=ordered_sections,
        continuing=[to_item(c) for c in continuing],
    )
    updated_memory = record_shipped(memory, kept, date, must_know_ids=must_know_ids)
    return edition, updated_memory


def build_and_write_edition(
    clusters: list[Cluster],
    memory: StoryMemory,
    date: str,
    llm: LLMClient | None = None,
    editions_dir: Path = EDITIONS_DIR,
    memory_path: Path = MEMORY_PATH,
) -> Path:
    if llm is None:
        from pipeline.gemini import GeminiClient

        llm = GeminiClient()

    edition, updated_memory = build_edition(clusters, memory, date, llm)

    editions_dir.mkdir(parents=True, exist_ok=True)
    out = editions_dir / f"{date}.json"
    out.write_text(edition.model_dump_json(indent=2))
    save_memory(updated_memory, memory_path)
    return out
