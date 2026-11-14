"""SQLModel persistence and atomic temporal updates."""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.engine import URL
from sqlmodel import Session, SQLModel, create_engine, select

from backend.models import Event, EventCreate, MemoryCreate, MemoryFact, MemorySupersede


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class InvalidReference(Exception):
    pass


class Store:
    def __init__(self, path: Path):
        self.path = path
        url = URL.create("sqlite+pysqlite", database=str(path.resolve()))
        self.engine = create_engine(url, connect_args={"check_same_thread": False})

        @sqlalchemy_event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        SQLModel.metadata.create_all(self.engine)

    @staticmethod
    def _source_exists(session: Session, event_id: int, session_id: str) -> bool:
        return session.exec(
            select(Event.id).where(Event.id == event_id, Event.session_id == session_id)
        ).first() is not None

    def create_event(self, value: EventCreate) -> Event:
        row = Event(
            session_id=value.session_id,
            content=value.content,
            timestamp=value.timestamp or datetime.now(timezone.utc),
        )
        with Session(self.engine, expire_on_commit=False) as session:
            with session.begin():
                session.add(row)
                session.flush()
                session.refresh(row)
        return row

    def list_events(self, session_id: str) -> list[Event]:
        with Session(self.engine) as session:
            return list(session.exec(
                select(Event).where(Event.session_id == session_id)
                .order_by(Event.timestamp, Event.id)
            ).all())

    def create_memory(self, value: MemoryCreate) -> MemoryFact:
        row = MemoryFact(
            session_id=value.session_id,
            subject=value.subject,
            predicate=value.predicate,
            object=value.object,
            valid_from=value.valid_from,
            valid_to=value.valid_to,
            source_event_id=value.source_event_id,
            status="historical" if value.valid_to else "current",
        )
        with Session(self.engine, expire_on_commit=False) as session:
            with session.begin():
                if not self._source_exists(session, value.source_event_id, value.session_id):
                    raise InvalidReference("source event does not exist in this session")
                session.add(row)
                session.flush()
                session.refresh(row)
        return row

    def list_memories(self, session_id: str, include_history: bool = False) -> list[MemoryFact]:
        statement = select(MemoryFact).where(MemoryFact.session_id == session_id)
        if not include_history:
            statement = statement.where(MemoryFact.status == "current")
        with Session(self.engine) as session:
            return list(session.exec(statement.order_by(MemoryFact.valid_from, MemoryFact.id)).all())

    def supersede(self, memory_id: int, value: MemorySupersede) -> MemoryFact:
        with Session(self.engine, expire_on_commit=False) as session:
            # Lock before reading the old fact so concurrent replacements serialize.
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                old = session.get(MemoryFact, memory_id)
                if old is None or old.session_id != value.session_id:
                    raise NotFound("memory does not exist in this session")
                if old.status != "current" or old.valid_to is not None:
                    raise Conflict("memory is no longer current")
                if value.valid_from <= old.valid_from:
                    raise Conflict("new valid_from must be later than the old valid_from")
                if not self._source_exists(session, value.source_event_id, value.session_id):
                    raise InvalidReference("source event does not exist in this session")

                old.valid_to = value.valid_from
                old.status = "superseded"
                new = MemoryFact(
                    session_id=value.session_id,
                    subject=value.subject,
                    predicate=value.predicate,
                    object=value.object,
                    valid_from=value.valid_from,
                    valid_to=None,
                    source_event_id=value.source_event_id,
                    status="current",
                )
                session.add(new)
                session.flush()
                session.refresh(new)
                session.commit()
            except Exception:
                session.rollback()
                raise
        return new
