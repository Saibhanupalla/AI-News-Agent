"""Rolling 7-day story memory: what we already shipped, so we never reship it."""

from datetime import datetime, timedelta
from pathlib import Path

from pipeline.models import Cluster, MemoryEntry, StoryMemory

RETENTION_DAYS = 7


def load_memory(path: Path) -> StoryMemory:
    if not path.exists():
        return StoryMemory()
    return StoryMemory.model_validate_json(path.read_text())


def save_memory(memory: StoryMemory, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(memory.model_dump_json(indent=2))


def prune_memory(memory: StoryMemory, today: str) -> StoryMemory:
    cutoff = datetime.strptime(today, "%Y-%m-%d") - timedelta(days=RETENTION_DAYS)
    kept = [
        entry
        for entry in memory.entries
        if datetime.strptime(entry.last_shipped, "%Y-%m-%d") > cutoff
    ]
    return StoryMemory(entries=kept)


def record_shipped(
    memory: StoryMemory,
    clusters: list[Cluster],
    today: str,
    must_know_ids: set[str] | None = None,
) -> StoryMemory:
    """Append today's shipped clusters, updating entries that share an event_key."""
    must_know_ids = must_know_ids or set()
    by_event = {entry.event_key: entry for entry in memory.entries}

    for cluster in clusters:
        event_key = cluster.event_key or cluster.cluster_id
        existing = by_event.get(event_key)
        if existing is not None:
            existing.urls = sorted(set(existing.urls) | set(cluster.urls))
            existing.last_shipped = today
            existing.last_summary = cluster.summary or existing.last_summary
            existing.was_must_know = existing.was_must_know or (
                cluster.cluster_id in must_know_ids
            )
        else:
            entry = MemoryEntry(
                event_key=event_key,
                urls=cluster.urls,
                title=cluster.title,
                first_seen=today,
                last_shipped=today,
                last_summary=cluster.summary,
                was_must_know=cluster.cluster_id in must_know_ids,
            )
            memory.entries.append(entry)
            by_event[event_key] = entry

    return memory


def memory_urls(memory: StoryMemory) -> set[str]:
    urls: set[str] = set()
    for entry in memory.entries:
        urls.update(entry.urls)
    return urls
