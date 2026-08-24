"""Pydantic schemas shared across pipeline stages."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

TOPIC_IDS = [
    "foundation-models",
    "research",
    "startups-funding",
    "policy",
    "open-source",
    "hardware",
    "tools",
    "big-tech",
]

TOPIC_LABELS = {
    "foundation-models": "Foundation models",
    "research": "Research",
    "startups-funding": "Startups and funding",
    "policy": "Policy and regulation",
    "open-source": "Open source",
    "hardware": "Hardware / chips",
    "tools": "Tools and products",
    "big-tech": "Big Tech",
}


class Feed(BaseModel):
    name: str
    url: str
    source_weight: float = 0.5
    max_age_hours: int = 36


class Article(BaseModel):
    id: str
    title: str
    url: str
    canonical_url: str
    source: str
    published_at: datetime | None = None
    snippet: str = ""
    source_weight: float = 0.5
    max_age_hours: int = 36


class FreshnessLabel(StrEnum):
    NEW = "new"
    POSSIBLE_UPDATE = "possible_update"


class StoryType(StrEnum):
    NEWS = "news"
    UPDATE = "update"
    OPINION = "opinion"
    EVERGREEN = "evergreen"


class Cluster(BaseModel):
    cluster_id: str
    title: str
    articles: list[Article]
    freshness: FreshnessLabel = FreshnessLabel.NEW
    # Filled by the quality gate (heuristics), refined by the LLM.
    topic_ids: list[str] = Field(default_factory=list)
    quality_score: float = 0.0
    # Filled by the LLM stage.
    summary: str = ""
    why_it_matters: str = ""
    story_type: StoryType | None = None
    novelty: float | None = None
    reader_value: float | None = None
    event_key: str = ""
    update_delta: str = ""
    # For possible_update clusters: the summary previously shipped for this event.
    previous_summary: str = ""

    @property
    def urls(self) -> list[str]:
        return [a.canonical_url for a in self.articles]

    @property
    def sources(self) -> list[str]:
        seen: dict[str, None] = {}
        for a in self.articles:
            seen.setdefault(a.source, None)
        return list(seen)

    @property
    def best_weight(self) -> float:
        return max((a.source_weight for a in self.articles), default=0.0)


class DropReason(StrEnum):
    DUPLICATE_URL = "duplicate_url"
    DUPLICATE_TITLE = "duplicate_title"
    STALE = "stale"
    EVERGREEN = "evergreen"
    OFF_TOPIC = "off_topic"
    LOW_QUALITY = "low_quality"
    NO_NEW_FACT = "no_new_fact"
    LOW_READER_VALUE = "low_reader_value"


class MemoryEntry(BaseModel):
    event_key: str
    urls: list[str]
    title: str
    first_seen: str  # YYYY-MM-DD
    last_shipped: str  # YYYY-MM-DD
    last_summary: str = ""
    was_must_know: bool = False


class StoryMemory(BaseModel):
    entries: list[MemoryEntry] = Field(default_factory=list)


class EditionItem(BaseModel):
    cluster_id: str
    title: str
    summary: str
    why_it_matters: str = ""
    topic_ids: list[str]
    story_type: StoryType
    update_delta: str = ""
    sources: list[dict[str, str]]  # [{"name": ..., "url": ...}]


class Edition(BaseModel):
    date: str  # YYYY-MM-DD
    intro: str
    must_know: list[EditionItem]
    sections: dict[str, list[EditionItem]]  # topic_id -> items
    continuing: list[EditionItem]
