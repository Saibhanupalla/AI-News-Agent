"""Pipeline orchestrator: ingest -> cluster -> freshness -> quality -> LLM -> edition."""

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pipeline.cluster import cluster_articles
from pipeline.config import MEMORY_PATH, RAW_DIR, load_feeds
from pipeline.freshness import apply_freshness
from pipeline.http import HttpxFetcher
from pipeline.ingest import ingest_all
from pipeline.memory import load_memory, prune_memory
from pipeline.models import Article
from pipeline.quality import FeedHealth, apply_quality

logger = logging.getLogger(__name__)


def resolve_date(raw: str) -> str:
    if raw == "today":
        return datetime.now(UTC).strftime("%Y-%m-%d")
    return raw


def write_articles(articles: list[Article], date: str, raw_dir: Path = RAW_DIR) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = raw_dir / f"{date}.json"
    payload = [a.model_dump(mode="json") for a in articles]
    out.write_text(json.dumps(payload, indent=2))
    return out


def run_command(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    date = resolve_date(args.date)

    if args.command == "ingest":
        articles = ingest_all(load_feeds(), HttpxFetcher())
        out = write_articles(articles, date)
        print(f"wrote {len(articles)} articles to {out}")
        return 0

    if args.command == "run":
        articles = ingest_all(load_feeds(), HttpxFetcher())
        clusters = cluster_articles(articles)
        logger.info("clustered %d articles into %d clusters", len(articles), len(clusters))

        memory = prune_memory(load_memory(MEMORY_PATH), date)
        now = datetime.now(UTC)
        fresh, fresh_drops = apply_freshness(clusters, memory, now)
        logger.info("freshness kept %d, dropped %d", len(fresh), len(fresh_drops))

        health = FeedHealth()
        survivors, quality_drops = apply_quality(fresh, health=health)
        logger.info("quality kept %d, dropped %d", len(survivors), len(quality_drops))
        logger.info("feed health: %s", json.dumps(health.as_dict(), indent=2))

        if getattr(args, "no_llm", False):
            print(f"[no-llm] {len(survivors)} clusters survive the gates for {date}:")
            for cluster in survivors:
                label = cluster.freshness.value
                topics = ",".join(cluster.topic_ids)
                print(f"  [{label}] ({topics}) {cluster.title}  <{len(cluster.sources)} src>")
            return 0

        from pipeline.edition import build_and_write_edition  # phase 6

        edition_path = build_and_write_edition(survivors, memory, date)
        print(f"wrote edition to {edition_path}")
        return 0

    return 1
