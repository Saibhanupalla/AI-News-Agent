"""Real Gemini implementation of the LLM seam. Only this module talks to Google."""

import json
import os
from pathlib import Path

from pipeline.config import REPO_ROOT
from pipeline.llm import ClusterAnnotation, EditorialDecision
from pipeline.models import TOPIC_IDS, TOPIC_LABELS, Cluster

ANNOTATE_MODEL = "gemini-3.1-flash-lite"
EDITORIAL_MODEL = "gemini-3.1-flash-lite"


class MissingApiKeyError(RuntimeError):
    pass


def load_api_key(env_file: Path | None = None) -> str:
    """GEMINI_API_KEY from the environment, falling back to a local .env file."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_file is None:
        env_file = REPO_ROOT / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
                break
    if not key:
        raise MissingApiKeyError(
            "GEMINI_API_KEY is not set. Export it or add it to .env "
            "(see .env.example). Use `run --no-llm` to skip the LLM stage."
        )
    return key


def _cluster_payload(cluster: Cluster) -> dict:
    return {
        "cluster_id": cluster.cluster_id,
        "title": cluster.title,
        "sources": cluster.sources,
        "snippets": [a.snippet[:400] for a in cluster.articles[:4]],
        "freshness": cluster.freshness.value,
        "previous_summary": cluster.previous_summary or None,
    }


ANNOTATE_PROMPT = f"""You are the editor of a daily AI/tech news briefing.
For every cluster below, return one annotation object.

Rules:
- topic_ids: pick 1-3 from exactly this list: {json.dumps(TOPIC_IDS)}
  ({json.dumps(TOPIC_LABELS)})
- summary: 1-2 factual sentences, no hype, based only on the given title/snippets.
- why_it_matters: one short sentence for a busy reader (may be empty for minor items).
- story_type: "news" (something happened), "update" (development in a known story),
  "opinion", or "evergreen" (listicle/how-to/undated content).
- novelty: 0-1, how new this is versus the previous_summary if one is given.
- reader_value: 0-1, how much a reader who chose AI/tech news would want this today.
- event_key: short-slug for the underlying event, e.g. "openai-gpt6-launch".
- update_delta: ONLY for clusters with freshness "possible_update": one sentence stating
  the genuinely new fact versus previous_summary. If there is no new fact, return "".

Clusters:
"""

EDITORIAL_PROMPT = """You are finalizing today's AI/tech briefing.
Given the annotated stories below, return:
- intro: exactly 2-3 short sentences framing the day, plain language, no hashtags.
- must_know_cluster_ids: the 3 most important cluster_ids (fewer if fewer stories).
- section_order: the topic_ids present, ordered by today's importance.

Stories:
"""


class GeminiClient:
    """Implements the LLMClient protocol with two batched structured-output calls."""

    def __init__(self, api_key: str | None = None) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key or load_api_key(REPO_ROOT / ".env"))

    def annotate_clusters(self, clusters: list[Cluster]) -> list[ClusterAnnotation]:
        payload = json.dumps([_cluster_payload(c) for c in clusters], indent=1)
        response = self._client.models.generate_content(
            model=ANNOTATE_MODEL,
            contents=ANNOTATE_PROMPT + payload,
            config={
                "response_mime_type": "application/json",
                "response_schema": list[ClusterAnnotation],
            },
        )
        annotations: list[ClusterAnnotation] = response.parsed or []
        by_id = {a.cluster_id: a for a in annotations}
        return [by_id[c.cluster_id] for c in clusters if c.cluster_id in by_id]

    def editorial(self, clusters: list[Cluster]) -> EditorialDecision:
        stories = [
            {
                "cluster_id": c.cluster_id,
                "title": c.title,
                "summary": c.summary,
                "topic_ids": c.topic_ids,
                "story_type": c.story_type.value if c.story_type else "news",
                "reader_value": c.reader_value,
            }
            for c in clusters
        ]
        response = self._client.models.generate_content(
            model=EDITORIAL_MODEL,
            contents=EDITORIAL_PROMPT + json.dumps(stories, indent=1),
            config={
                "response_mime_type": "application/json",
                "response_schema": EditorialDecision,
            },
        )
        decision = response.parsed
        if decision is None:
            raise RuntimeError("Gemini editorial call returned no parseable decision")
        return decision
