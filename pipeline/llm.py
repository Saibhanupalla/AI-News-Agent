"""LLM seam. The pipeline depends on this protocol; tests inject a fake.

The real Gemini implementation lands in the edition stage (phase 6).
"""

from typing import Protocol

from pydantic import BaseModel

from pipeline.models import Cluster, StoryType


class ClusterAnnotation(BaseModel):
    """Per-cluster judgment from the LLM (batch 1)."""

    cluster_id: str
    topic_ids: list[str]
    summary: str
    why_it_matters: str = ""
    story_type: StoryType
    novelty: float
    reader_value: float
    event_key: str
    # For possible_update clusters: empty string means "no new fact, drop it".
    update_delta: str = ""


class EditorialDecision(BaseModel):
    """Edition-level judgment from the LLM (batch 2)."""

    intro: str
    must_know_cluster_ids: list[str]
    section_order: list[str]


class LLMClient(Protocol):
    def annotate_clusters(self, clusters: list[Cluster]) -> list[ClusterAnnotation]:
        """One batched call: tag, summarize, and score every cluster."""
        ...

    def editorial(self, clusters: list[Cluster]) -> EditorialDecision:
        """One call: pick top stories, order sections, write the intro."""
        ...
