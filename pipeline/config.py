"""Paths and feed configuration."""

import json
from pathlib import Path

from pipeline.models import Feed

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
FEEDS_PATH = DATA_DIR / "feeds.json"
EDITIONS_DIR = DATA_DIR / "editions"
MEMORY_PATH = DATA_DIR / "memory" / "recent_stories.json"
RAW_DIR = DATA_DIR / "raw"


def load_feeds(path: Path = FEEDS_PATH) -> list[Feed]:
    payload = json.loads(path.read_text())
    return [Feed.model_validate(entry) for entry in payload["feeds"]]
