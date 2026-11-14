"""SQLModel tables and validated API inputs."""

from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import CheckConstraint, Column, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field as DBField, SQLModel


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(timezone.utc)


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventCreate(InputModel):
    session_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    timestamp: datetime | None = None

    @field_validator("session_id", "content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("timestamp")
    @classmethod
    def timestamp_utc(cls, value: datetime | None) -> datetime | None:
        return aware_utc(value) if value is not None else None


class UTCDateTime(TypeDecorator):
    """Store timestamps as sortable, fixed-precision UTC ISO 8601 text."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> str | None:
        if value is None:
            return None
        return aware_utc(value).isoformat(timespec="microseconds")

    def process_result_value(self, value: str | None, dialect: object) -> datetime | None:
        return datetime.fromisoformat(value) if value is not None else None


class Event(SQLModel, table=True):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("id", "session_id"),
        Index("events_session_time", "session_id", "timestamp", "id"),
    )

    id: int | None = DBField(default=None, primary_key=True)
    session_id: str
    content: str
    timestamp: datetime = DBField(sa_column=Column(UTCDateTime(), nullable=False))


class MemoryCreate(InputModel):
    session_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    valid_from: datetime
    valid_to: datetime | None = None
    source_event_id: int = Field(gt=0)

    @field_validator("session_id", "subject", "predicate", "object")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("valid_from", "valid_to")
    @classmethod
    def time_utc(cls, value: datetime | None) -> datetime | None:
        return aware_utc(value) if value is not None else None

    @model_validator(mode="after")
    def interval_is_positive(self) -> "MemoryCreate":
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")
        return self


class MemorySupersede(InputModel):
    session_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    valid_from: datetime
    source_event_id: int = Field(gt=0)

    @field_validator("session_id", "subject", "predicate", "object")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("valid_from")
    @classmethod
    def time_utc(cls, value: datetime) -> datetime:
        return aware_utc(value)


class MemoryFact(SQLModel, table=True):
    __tablename__ = "memories"
    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from"),
        CheckConstraint("status IN ('current', 'superseded', 'historical')"),
        ForeignKeyConstraint(
            ["source_event_id", "session_id"], ["events.id", "events.session_id"]
        ),
        Index("memories_session_status", "session_id", "status", "id"),
    )

    id: int | None = DBField(default=None, primary_key=True)
    session_id: str
    subject: str
    predicate: str
    object: str
    valid_from: datetime = DBField(sa_column=Column(UTCDateTime(), nullable=False))
    valid_to: datetime | None = DBField(default=None, sa_column=Column(UTCDateTime(), nullable=True))
    source_event_id: int
    status: str
