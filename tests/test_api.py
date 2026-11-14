"""API and persistence contract tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app

SESSION = "session-a"
T1 = "2026-01-01T12:00:00Z"
T2 = "2026-01-02T12:00:00Z"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "continuum.sqlite3"


@pytest.fixture
def client(db_path: Path):
    with TestClient(create_app(db_path)) as test_client:
        yield test_client


def event(client: TestClient, session: str = SESSION, content: str = "First event", timestamp: str = T1) -> dict:
    response = client.post("/events", json={
        "session_id": session, "content": content, "timestamp": timestamp,
    })
    assert response.status_code == 201
    return response.json()


def memory(client: TestClient, source_event_id: int, session: str = SESSION, **changes) -> dict:
    payload = {
        "session_id": session, "subject": "user", "predicate": "prefers",
        "object": "graph neural networks", "valid_from": T1,
        "source_event_id": source_event_id,
    }
    payload.update(changes)
    response = client.post("/memories", json=payload)
    assert response.status_code == 201
    return response.json()


def test_health_and_event_creation_retrieval_persistence(client: TestClient, db_path: Path) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    created = event(client)
    assert created["id"] > 0
    assert created["session_id"] == SESSION
    assert created["content"] == "First event"
    assert client.get("/events", params={"session_id": SESSION}).json() == [created]
    with TestClient(create_app(db_path)) as reopened:
        assert reopened.get("/events", params={"session_id": SESSION}).json() == [created]


def test_memory_persistence_and_source_provenance(client: TestClient, db_path: Path) -> None:
    source = event(client)
    fact = memory(client, source["id"])
    assert fact["source_event_id"] == source["id"]
    assert fact["status"] == "current"
    assert fact["valid_to"] is None
    with TestClient(create_app(db_path)) as reopened:
        assert reopened.get("/memories", params={"session_id": SESSION}).json() == [fact]
        assert reopened.get("/events", params={"session_id": SESSION}).json() == [source]


def test_supersession_and_historical_retrieval(client: TestClient) -> None:
    first = event(client)
    old = memory(client, first["id"])
    second = event(client, content="I prefer interpretable ML", timestamp=T2)
    response = client.post(f"/memories/{old['id']}/supersede", json={
        "session_id": SESSION, "subject": "user", "predicate": "prefers",
        "object": "interpretable ML", "valid_from": T2,
        "source_event_id": second["id"],
    })
    assert response.status_code == 201
    new = response.json()
    assert new["source_event_id"] == second["id"]
    assert new["status"] == "current"
    assert client.get("/memories", params={"session_id": SESSION}).json() == [new]
    history = client.get("/memories", params={
        "session_id": SESSION, "include_history": "true",
    }).json()
    assert len(history) == 2
    assert history[0]["id"] == old["id"]
    assert history[0]["valid_to"] == new["valid_from"]
    assert history[0]["status"] == "superseded"
    assert history[0]["source_event_id"] == first["id"]
    assert history[1] == new
    assert client.post(f"/memories/{old['id']}/supersede", json={
        "session_id": SESSION, "subject": "user", "predicate": "prefers",
        "object": "another", "valid_from": "2026-01-03T12:00:00Z",
        "source_event_id": second["id"],
    }).status_code == 409


def test_invalid_references_and_atomic_supersession(client: TestClient) -> None:
    first = event(client)
    old = memory(client, first["id"])
    payload = {"session_id": SESSION, "subject": "user", "predicate": "prefers",
               "object": "new", "valid_from": T2, "source_event_id": 99999}
    assert client.post("/memories", json=payload).status_code == 422
    assert client.post(f"/memories/{old['id']}/supersede", json=payload).status_code == 422
    assert client.get("/memories", params={"session_id": SESSION}).json() == [old]
    assert client.post(f"/memories/{old['id']}/supersede", json={
        **payload, "source_event_id": first["id"], "valid_from": T1,
    }).status_code == 409
    assert client.get("/memories", params={"session_id": SESSION}).json() == [old]


def test_session_scoped_reads_and_writes(client: TestClient) -> None:
    first = event(client, session=SESSION)
    other = event(client, session="session-b", content="Other")
    assert client.get("/events", params={"session_id": SESSION}).json() == [first]
    assert client.get("/events", params={"session_id": "session-b"}).json() == [other]
    assert client.get("/events").status_code == 422
    assert client.get("/memories").status_code == 422
    assert client.post("/memories", json={
        "session_id": SESSION, "subject": "user", "predicate": "prefers",
        "object": "wrong source", "valid_from": T1,
        "source_event_id": other["id"],
    }).status_code == 422
    fact = memory(client, first["id"])
    assert client.get("/memories", params={"session_id": "session-b"}).json() == []
    assert client.post(f"/memories/{fact['id']}/supersede", json={
        "session_id": "session-b", "subject": "user", "predicate": "prefers",
        "object": "other", "valid_from": T2, "source_event_id": other["id"],
    }).status_code == 404
    assert client.post(f"/memories/{fact['id']}/supersede", json={
        "session_id": SESSION, "subject": "user", "predicate": "prefers",
        "object": "other", "valid_from": T2, "source_event_id": other["id"],
    }).status_code == 422
    assert client.get("/memories", params={"session_id": SESSION}).json() == [fact]


def test_invalid_intervals_and_explicit_independent_facts(client: TestClient) -> None:
    source = event(client)
    for end in (T1, "2025-12-31T12:00:00Z"):
        response = client.post("/memories", json={
            "session_id": SESSION, "subject": "user", "predicate": "prefers",
            "object": "bad", "valid_from": T1, "valid_to": end,
            "source_event_id": source["id"],
        })
        assert response.status_code == 422
    assert client.post("/memories", json={
        "session_id": SESSION, "subject": "user", "predicate": "prefers",
        "object": "bad", "valid_from": "2026-01-01T12:00:00",
        "source_event_id": source["id"],
    }).status_code == 422
    first = memory(client, source["id"])
    second = memory(client, source["id"], object="interpretable ML")
    assert [item["id"] for item in client.get("/memories", params={
        "session_id": SESSION,
    }).json()] == [first["id"], second["id"]]
