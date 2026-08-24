"""Pipeline orchestrator. Stages are wired in as phases land."""

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import RAW_DIR, load_feeds
from pipeline.http import HttpxFetcher
from pipeline.ingest import ingest_all
from pipeline.models import Article

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
        print(f"[stub] full run for {date}: implemented in phases 3-6")
        return 0

    return 1
