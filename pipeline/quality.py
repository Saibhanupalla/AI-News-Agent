"""Quality and relevance gate: keep news an AI/tech reader asked for, drop junk.

Runs before any LLM call so we never spend tokens on listicles. Heuristics only;
the LLM stage refines topics and adds reader-value scores for what survives.
"""

import logging
import re
from collections import defaultdict

from pipeline.models import Cluster, DropReason

logger = logging.getLogger(__name__)

MAX_CLUSTERS = 15
# Single-source stories from low-weight feeds are usually vendor noise.
SINGLE_SOURCE_MIN_WEIGHT = 0.6
MULTI_SOURCE_BONUS = 0.15

EVERGREEN_PATTERNS = [
    r"^\d+\s+(best|top|great|essential|must)",
    r"\b(best|top)\s+\d+\b",
    r"\b\d+\s+(ai\s+)?tools\b",
    r"\btools?\s+to\s+try\b",
    r"\bhow\s+to\b",
    r"\bguide\s+to\b",
    r"\b(roundup|listicle|ranked)\b",
    r"\b(deal|deals|discount|coupon|sale)\b",
    r"\b(webinar|hiring|job\s+board|we're\s+hiring|careers)\b",
    r"\bthis\s+week\s+in\b",
    r"\bweekly\s+recap\b",
]

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "foundation-models": [
        "gpt", "claude", "gemini", "llama", "model", "llm", "frontier",
        "multimodal", "context window", "reasoning",
    ],
    "research": [
        "research", "paper", "arxiv", "study", "benchmark", "breakthrough",
        "attention", "training", "dataset",
    ],
    "startups-funding": [
        "raises", "funding", "round", "seed", "series a", "series b", "series c",
        "valuation", "acquires", "acquisition", "ipo", "startup",
    ],
    "policy": [
        "regulation", "regulator", "policy", "law", "lawsuit", "act", "bill",
        "congress", "senate", "parliament", "eu", "ban", "antitrust", "liability",
        "copyright", "court", "ruling",
    ],
    "open-source": [
        "open source", "open-source", "open weights", "hugging face", "github",
        "apache", "mit license", "weights released",
    ],
    "hardware": [
        "chip", "chips", "gpu", "gpus", "semiconductor", "nvidia", "tsmc",
        "datacenter", "data center", "wafer", "inference hardware", "accelerator",
    ],
    "tools": [
        "launches", "launch", "app", "feature", "product", "api", "tool",
        "assistant", "agent", "integration", "update",
    ],
    "big-tech": [
        "google", "microsoft", "apple", "amazon", "meta", "openai", "anthropic",
        "deepmind", "nvidia", "tesla", "samsung",
    ],
}

# A cluster must also look like AI/tech news at all; otherwise it is off-topic
# regardless of accidental keyword hits.
RELEVANCE_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "model", "llm", "chip",
    "software", "compute", "robot", "neural", "algorithm", "tech", "data",
    "startup", "gpt", "chatbot", "agent", "semiconductor", "cloud", "api",
]


def _text_of(cluster: Cluster) -> str:
    parts = [cluster.title]
    parts.extend(a.snippet for a in cluster.articles)
    return " ".join(parts).lower()


def is_evergreen(cluster: Cluster) -> bool:
    title = cluster.title.lower()
    return any(re.search(pattern, title) for pattern in EVERGREEN_PATTERNS)


def is_relevant(cluster: Cluster) -> bool:
    text = _text_of(cluster)
    return any(re.search(rf"\b{re.escape(kw)}\b", text) for kw in RELEVANCE_KEYWORDS)


def tag_topics(cluster: Cluster) -> list[str]:
    text = _text_of(cluster)
    tags = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(kw)}\b", text) for kw in keywords):
            tags.append(topic)
    return tags


def score_cluster(cluster: Cluster) -> float:
    independent_sources = len(cluster.sources)
    bonus = MULTI_SOURCE_BONUS * (independent_sources - 1)
    return min(1.0, cluster.best_weight + bonus)


class FeedHealth:
    """Per-source drop counters so junk feeds can be demoted after a week of runs."""

    def __init__(self) -> None:
        self.counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def record(self, cluster: Cluster, reason: DropReason) -> None:
        for source in cluster.sources:
            self.counts[source][reason.value] += 1

    def as_dict(self) -> dict[str, dict[str, int]]:
        return {source: dict(reasons) for source, reasons in self.counts.items()}


def apply_quality(
    clusters: list[Cluster],
    health: FeedHealth | None = None,
) -> tuple[list[Cluster], list[tuple[Cluster, DropReason]]]:
    health = health or FeedHealth()
    kept: list[Cluster] = []
    dropped: list[tuple[Cluster, DropReason]] = []

    for cluster in clusters:
        if is_evergreen(cluster):
            dropped.append((cluster, DropReason.EVERGREEN))
        elif not is_relevant(cluster) or not (topics := tag_topics(cluster)):
            dropped.append((cluster, DropReason.OFF_TOPIC))
        elif len(cluster.sources) == 1 and cluster.best_weight < SINGLE_SOURCE_MIN_WEIGHT:
            dropped.append((cluster, DropReason.LOW_QUALITY))
        else:
            cluster.topic_ids = topics
            cluster.quality_score = score_cluster(cluster)
            kept.append(cluster)

    for cluster, reason in dropped:
        health.record(cluster, reason)
        logger.info("quality drop [%s]: %s", reason.value, cluster.title)

    kept.sort(key=lambda c: c.quality_score, reverse=True)
    if len(kept) > MAX_CLUSTERS:
        for overflow in kept[MAX_CLUSTERS:]:
            dropped.append((overflow, DropReason.LOW_QUALITY))
            health.record(overflow, DropReason.LOW_QUALITY)
        kept = kept[:MAX_CLUSTERS]

    return kept, dropped
