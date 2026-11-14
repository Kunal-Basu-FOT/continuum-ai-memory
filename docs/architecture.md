# Milestone 1 architecture

## Components

- `backend/main.py` defines the five HTTP route groups and maps domain errors to HTTP responses.
- `backend/models.py` defines the `Event` and `MemoryFact` SQLModel tables, typed request models, and validation for text, timezone-aware timestamps, and intervals.
- `backend/storage.py` uses SQLModel sessions for SQLite schema creation, queries, provenance checks, and transactional supersession.
- `backend/config.py` reads the SQLite path from `CONTINUUM_DATABASE_PATH`.
- `backend/seed.py` creates a fixed two-event example in a fresh demo session.

## Data model

`events` has an integer `id`, `session_id`, `content`, and UTC `timestamp`. An event is an immutable record of supplied text. The service does not extract facts from that text.

`memories` has an integer `id`, `session_id`, `subject`, `predicate`, `object`, `valid_from`, nullable `valid_to`, `source_event_id`, and `status`. Intervals are half-open: `[valid_from, valid_to)`, or open-ended when `valid_to` is null. Status is `current` for open-ended facts, `historical` for facts created with a finite interval, and `superseded` for a fact closed by an explicit replacement. A composite foreign key on `(source_event_id, session_id)` references `(events.id, events.session_id)`, so every fact has an existing source in its own session. Every SQLite connection enables foreign key enforcement.

All supplied timestamps must include a timezone and are stored as fixed-precision UTC ISO 8601 strings. This makes SQLite string ordering match chronological ordering. The API and schema both reject an interval whose end is not later than its start.

## Temporal behavior

The API never interprets matching predicates as contradictory. Creating another `prefers` fact leaves existing facts alone. To replace one, the caller names its ID via `POST /memories/{id}/supersede`, supplies a same-session source event, and gives a `valid_from` strictly later than the old fact's start. The store starts an `IMMEDIATE` SQLite transaction, verifies that the named fact is current, closes it at the new start, inserts the replacement, and commits. Any error rolls the transaction back. A second attempt to supersede the same fact returns a conflict.

`GET /memories?session_id=...` returns current facts. Add `include_history=true` to retrieve all facts, including finite and superseded ones. `GET /events` and both memory reads require a session ID. A supersession request with an ID from another session returns 404; a source event from another session is rejected.

## Limitations

Session IDs are caller-supplied filters, not authentication or authorization. There is no user identity or access control. The service does not enforce a single fact per subject/predicate, infer contradiction, decide whether event text supports a fact, or guarantee that a fact's validity starts at the event timestamp. There is no graph database, LLM, frontend, migration framework, pagination, or production concurrency strategy beyond SQLite's write serialization. Schema creation is intended for a fresh Milestone 1 database; future schema changes need migrations.
