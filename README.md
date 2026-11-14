# Continuum

Milestone 1 is a small FastAPI and SQLModel service for storing conversation events and sourced, time-bounded memory facts in SQLite. It makes no automatic inferences from event text.

## Install and run

Use Python 3.11 or newer:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn backend.main:app --reload
```

On macOS or Linux, activate with `source .venv/bin/activate`. The API is at `http://127.0.0.1:8000`; interactive OpenAPI docs are at `/docs`.

Set `CONTINUUM_DATABASE_PATH` to choose a SQLite file. Its default is `data/continuum.sqlite3`. The directory is created at startup. SQLite files and `.env` files are ignored by Git.

## API example

Each read requires a `session_id`. Session IDs are demo-level scoping and provide no authentication.

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/events -H "Content-Type: application/json" -d '{"session_id":"demo","content":"I am interested in graph neural networks.","timestamp":"2026-01-01T12:00:00Z"}'
curl 'http://127.0.0.1:8000/events?session_id=demo'
curl -X POST http://127.0.0.1:8000/memories -H "Content-Type: application/json" -d '{"session_id":"demo","subject":"user","predicate":"prefers","object":"graph neural networks","valid_from":"2026-01-01T12:00:00Z","source_event_id":1}'
curl 'http://127.0.0.1:8000/memories?session_id=demo'
```

After posting a newer event in the same session, replace a specific current fact with:

```bash
curl -X POST http://127.0.0.1:8000/memories/1/supersede -H "Content-Type: application/json" -d '{"session_id":"demo","subject":"user","predicate":"prefers","object":"interpretable ML","valid_from":"2026-01-02T12:00:00Z","source_event_id":2}'
curl 'http://127.0.0.1:8000/memories?session_id=demo&include_history=true'
```

The supersede operation closes memory `1` at the new fact's `valid_from` and creates a new current memory. The old fact remains available through `include_history=true`. Timestamps must include a timezone; storage normalizes them to UTC. Invalid intervals and missing or cross-session source events are rejected.

## Seed the example and test

```powershell
python -m backend.seed --database data/demo.sqlite3
python -m pytest -q
```

The seed uses fixed timestamps and the session `demo-temporal-update`. Run it against a fresh database; it refuses to add the example twice to that session.

See [architecture](docs/architecture.md) for the schema, temporal rules, and limitations.
