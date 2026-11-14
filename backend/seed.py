"""Seed the documented two-event example in a fresh demo session."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.config import database_path
from backend.models import EventCreate, MemoryCreate, MemorySupersede
from backend.storage import Store

DEMO_SESSION = "demo-temporal-update"


def seed(store: Store) -> dict[str, int]:
    store.initialize()
    if store.list_events(DEMO_SESSION):
        raise ValueError(f"session {DEMO_SESSION!r} already has events; use a fresh database")

    first_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    second_time = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    first = store.create_event(EventCreate(
        session_id=DEMO_SESSION,
        content="I am interested in graph neural networks.",
        timestamp=first_time,
    ))
    old = store.create_memory(MemoryCreate(
        session_id=DEMO_SESSION, subject="user", predicate="prefers",
        object="graph neural networks", valid_from=first_time,
        source_event_id=first.id,
    ))
    second = store.create_event(EventCreate(
        session_id=DEMO_SESSION,
        content="I no longer want to pursue GNNs because my dataset is too small. I prefer interpretable ML.",
        timestamp=second_time,
    ))
    new = store.supersede(old.id, MemorySupersede(
        session_id=DEMO_SESSION, subject="user", predicate="prefers",
        object="interpretable ML", valid_from=second_time,
        source_event_id=second.id,
    ))
    return {"first_event_id": first.id, "second_event_id": second.id,
            "old_memory_id": old.id, "new_memory_id": new.id}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=database_path())
    args = parser.parse_args()
    print(json.dumps(seed(Store(args.database)), indent=2))


if __name__ == "__main__":
    main()
