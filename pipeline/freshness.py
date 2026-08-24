"""Freshness gate: drop yesterday's stories, flag genuine follow-ups as updates.

Rules, cheapest first:
1. Stale: newest article in the cluster is older than its feed's max age
   (unknown publish dates count as stale).
2. Duplicate URL: any cluster URL was already shipped in the last 7 days.
3. Duplicate title: high similarity vs a shipped story. Not dropped here -
   labeled possible_update and the LLM stage decides (new fact -> update, else drop).
"""

import logging
from datetime import datetime, timedelta

from pipeline.cluster import titles_match
from pipeline.memory import memory_urls
from pipeline.models import Cluster, DropReason, FreshnessLabel, StoryMemory

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE_HOURS = 36


def cluster_age_ok(cluster: Cluster, now: datetime) -> bool:
    dated = [a for a in cluster.articles if a.published_at is not None]
    if not dated:
        return False
    newest = max(a.published_at for a in dated)  # type: ignore[type-var]
    # At cluster level, allow the most permissive window among member articles
    # (labs blogs get 48h, wire feeds 24-36h).
    max_age = max(a.max_age_hours for a in cluster.articles)
    return newest >= now - timedelta(hours=max_age)


def apply_freshness(
    clusters: list[Cluster],
    memory: StoryMemory,
    now: datetime,
) -> tuple[list[Cluster], list[tuple[Cluster, DropReason]]]:
    shipped_urls = memory_urls(memory)
    kept: list[Cluster] = []
    dropped: list[tuple[Cluster, DropReason]] = []

    for cluster in clusters:
        if not cluster_age_ok(cluster, now):
            dropped.append((cluster, DropReason.STALE))
            continue

        if any(url in shipped_urls for url in cluster.urls):
            dropped.append((cluster, DropReason.DUPLICATE_URL))
            continue

        matched_entry = next(
            (e for e in memory.entries if titles_match(cluster.title, e.title)),
            None,
        )
        if matched_entry is not None:
            cluster.freshness = FreshnessLabel.POSSIBLE_UPDATE
            cluster.event_key = matched_entry.event_key
            cluster.previous_summary = matched_entry.last_summary

        kept.append(cluster)

    for cluster, reason in dropped:
        logger.info("freshness drop [%s]: %s", reason.value, cluster.title)
    return kept, dropped
