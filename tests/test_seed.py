"""Deterministic example test."""

from backend.seed import DEMO_SESSION, seed
from backend.storage import Store


def test_seed(tmp_path) -> None:
    store = Store(tmp_path / "seed.sqlite3")
    ids = seed(store)
    assert ids == {"first_event_id": 1, "second_event_id": 2,
                   "old_memory_id": 1, "new_memory_id": 2}
    events = store.list_events(DEMO_SESSION)
    history = store.list_memories(DEMO_SESSION, include_history=True)
    assert len(events) == len(history) == 2
    assert history[0].valid_to == history[1].valid_from
    assert history[0].source_event_id == events[0].id
    assert history[1].source_event_id == events[1].id
