"""HTTP API for events and temporal memories."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, status

from backend.config import database_path
from backend.models import Event, EventCreate, MemoryCreate, MemoryFact, MemorySupersede
from backend.storage import Conflict, InvalidReference, NotFound, Store


def create_app(path: Path | None = None) -> FastAPI:
    store = Store(path or database_path())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.initialize()
        yield

    app = FastAPI(title="Continuum", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/events", response_model=Event, status_code=status.HTTP_201_CREATED)
    def create_event(value: EventCreate) -> Event:
        return store.create_event(value)

    @app.get("/events", response_model=list[Event])
    def list_events(session_id: str = Query(min_length=1)) -> list[Event]:
        return store.list_events(session_id)

    @app.post("/memories", response_model=MemoryFact, status_code=status.HTTP_201_CREATED)
    def create_memory(value: MemoryCreate) -> MemoryFact:
        try:
            return store.create_memory(value)
        except InvalidReference as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/memories", response_model=list[MemoryFact])
    def list_memories(
        session_id: str = Query(min_length=1), include_history: bool = False
    ) -> list[MemoryFact]:
        return store.list_memories(session_id, include_history)

    @app.post("/memories/{memory_id}/supersede", response_model=MemoryFact, status_code=201)
    def supersede(memory_id: int, value: MemorySupersede) -> MemoryFact:
        try:
            return store.supersede(memory_id, value)
        except NotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except Conflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except InvalidReference as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return app


app = create_app()
