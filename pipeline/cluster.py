"""Same-day dedupe and clustering: one event, one cluster, many source links."""

import hashlib
import re

from rapidfuzz import fuzz

from pipeline.models import Article, Cluster

# token_set_ratio ignores word order and duplication; 80 merges reworded headlines
# for the same event but keeps "launch" and "pricing rumor" stories apart.
TITLE_SIMILARITY_THRESHOLD = 80.0


def normalize_title(title: str) -> str:
    lowered = title.lower()
    lowered = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def titles_match(a: str, b: str) -> bool:
    norm_a, norm_b = normalize_title(a), normalize_title(b)
    # token_set_ratio scores subset matches at 100, so a 1-2 word title ("Universe",
    # "Healthcare") would merge with any headline containing it. Require a plain
    # ratio for short titles instead.
    if min(len(norm_a.split()), len(norm_b.split())) < 3:
        return fuzz.ratio(norm_a, norm_b) >= 95.0
    return fuzz.token_set_ratio(norm_a, norm_b) >= TITLE_SIMILARITY_THRESHOLD


def make_cluster_id(articles: list[Article]) -> str:
    joined = "|".join(sorted(a.canonical_url for a in articles))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def cluster_articles(articles: list[Article]) -> list[Cluster]:
    """Greedy clustering: exact canonical URL first, then fuzzy title match."""
    groups: list[list[Article]] = []
    by_url: dict[str, int] = {}

    for article in articles:
        if article.canonical_url in by_url:
            groups[by_url[article.canonical_url]].append(article)
            continue

        matched = None
        for index, group in enumerate(groups):
            if any(titles_match(article.title, member.title) for member in group):
                matched = index
                break

        if matched is None:
            groups.append([article])
            matched = len(groups) - 1
        else:
            groups[matched].append(article)
        by_url[article.canonical_url] = matched

    clusters = []
    for group in groups:
        # Represent the cluster with the most authoritative source's headline.
        lead = max(group, key=lambda a: a.source_weight)
        clusters.append(
            Cluster(
                cluster_id=make_cluster_id(group),
                title=lead.title,
                articles=group,
            )
        )
    return clusters
