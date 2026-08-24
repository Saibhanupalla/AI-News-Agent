"""Shared harness: fixture feeds, stub fetcher, fake LLM, frozen dates, temp data dir."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipeline.http import FeedFetchError
from pipeline.llm import ClusterAnnotation, EditorialDecision
from pipeline.models import Cluster, StoryType

FIXTURES = Path(__file__).parent / "fixtures"

# All feed fixtures are dated around this moment; freshness tests freeze "now" here.
FROZEN_NOW = datetime(2026, 8, 24, 8, 0, 0, tzinfo=UTC)
FROZEN_TODAY = "2026-08-24"


def fixture_feed(name: str) -> bytes:
    return (FIXTURES / "feeds" / name).read_bytes()


class StubFetcher:
    """Maps url -> fixture bytes. Unknown urls or planted errors raise FeedFetchError."""

    def __init__(self, responses: dict[str, bytes], errors: set[str] | None = None) -> None:
        self._responses = responses
        self._errors = errors or set()
        self.calls: list[str] = []

    def fetch(self, url: str) -> bytes:
        self.calls.append(url)
        if url in self._errors:
            raise FeedFetchError(f"{url}: planted failure")
        if url not in self._responses:
            raise FeedFetchError(f"{url}: no fixture registered")
        return self._responses[url]


class FakeLLM:
    """Records calls, returns canned annotations. Never touches the network."""

    def __init__(
        self,
        annotations: dict[str, ClusterAnnotation] | None = None,
        decision: EditorialDecision | None = None,
    ) -> None:
        self._annotations = annotations or {}
        self._decision = decision
        self.annotate_calls: list[list[str]] = []
        self.editorial_calls: list[list[str]] = []

    def annotate_clusters(self, clusters: list[Cluster]) -> list[ClusterAnnotation]:
        self.annotate_calls.append([c.cluster_id for c in clusters])
        results = []
        for cluster in clusters:
            if cluster.cluster_id in self._annotations:
                results.append(self._annotations[cluster.cluster_id])
            else:
                results.append(default_annotation(cluster))
        return results

    def editorial(self, clusters: list[Cluster]) -> EditorialDecision:
        self.editorial_calls.append([c.cluster_id for c in clusters])
        if self._decision is not None:
            return self._decision
        ranked = sorted(clusters, key=lambda c: c.reader_value or 0, reverse=True)
        return EditorialDecision(
            intro="Today's fixture briefing.",
            must_know_cluster_ids=[c.cluster_id for c in ranked[:3]],
            section_order=[],
        )


def default_annotation(cluster: Cluster) -> ClusterAnnotation:
    return ClusterAnnotation(
        cluster_id=cluster.cluster_id,
        topic_ids=["foundation-models"],
        summary=f"Summary of: {cluster.title}",
        why_it_matters="It matters for the fixture.",
        story_type=StoryType.NEWS,
        novelty=0.9,
        reader_value=0.8,
        event_key=cluster.cluster_id,
    )


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Isolated data/ tree so tests never touch the repo's real files."""
    (tmp_path / "editions").mkdir()
    (tmp_path / "memory").mkdir()
    (tmp_path / "raw").mkdir()
    return tmp_path
