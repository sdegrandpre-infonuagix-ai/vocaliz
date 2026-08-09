"""The durable side of `JournalStore` (NFR8).

Three tables owned by the orchestrator, which is the move Story 6.3 describes: the journal
stops being a per-Salon table the API writes captions into and becomes state the
orchestrator holds and persists. `api.utterances` keeps doing its own job — serving the
transcript of a Salon to a client — and neither writes the other's rows.

Written with SQLAlchemy Core rather than an ORM. There are three tables, no relationships
worth mapping, and every access is by primary key; a model layer would be ceremony around
four statements. It also keeps the SQL portable enough to be tested against SQLite, which
is why these tests need no database to run.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    select,
)
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import DateTime

from src.journal.journal import JournalEntry
from src.journal.store import SalonState

metadata = MetaData()


def _as_utc(moment: datetime) -> datetime:
    """Put the timezone back on a timestamp that lost it in the database.

    Postgres keeps it; SQLite has no timezone type and hands back a naive value. Attaching
    UTC is not a guess — the journal stamps every arrival with `datetime.now(tz=utc)` and
    nothing else writes this column — but leaving it naive would be. Story 6.10's one-year
    expiry is computed off this, and comparing a naive timestamp to an aware one raises
    rather than quietly being wrong, which is the only reason it has not already bitten.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)



# The journal. Primary key on (salon_id, sequence) rather than a surrogate id: the position
# of a message within its Salon is what identifies it everywhere else in this component,
# and the same key makes appending the same position twice an error the database catches.
journal_table = Table(
    "salon_journal",
    metadata,
    Column("salon_id", String(64), primary_key=True),
    Column("sequence", Integer, primary_key=True),
    Column("participant_id", String(128), nullable=False),
    Column("text", Text, nullable=False),
    Column("language", String(16), nullable=False, server_default=""),
    Column("arrived_at", DateTime(timezone=True), nullable=False),
    Column("duration_seconds", Float, nullable=False),
)

# One row per reader, overwritten as it advances. No history: where an interpreter used to
# be is of no interest to anybody, and keeping it would be keeping a record of how closely
# somebody was following a conversation.
cursor_table = Table(
    "salon_cursors",
    metadata,
    Column("salon_id", String(64), primary_key=True),
    Column("reader_id", String(128), primary_key=True),
    Column("position", Integer, nullable=False),
)

# Keyed on the pair, so a language several people are listening in is stored once.
translation_table = Table(
    "salon_translations",
    metadata,
    Column("salon_id", String(64), primary_key=True),
    Column("sequence", Integer, primary_key=True),
    Column("language", String(16), primary_key=True),
    Column("text", Text, nullable=False),
)


def async_url(database_url: str) -> str:
    """Name the async driver in a URL that does not.

    `DATABASE_URL` is shared with the API, which reads it synchronously through psycopg,
    and `postgresql://` means exactly that to SQLAlchemy. Handing it to
    `create_async_engine` unchanged fails at startup with a message about a missing
    greenlet, which says nothing about the actual mistake. Two configuration entries for
    one database would be worse: they would eventually disagree.
    """
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


class SqlJournalStore:
    """`JournalStore` over any database SQLAlchemy speaks, asynchronously."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create_all(self) -> None:
        """Create the three tables if they are not there.

        Called at startup. The orchestrator owns this schema outright and it is three
        tables with no history to migrate, so a migration tool would be one more thing to
        run for a `CREATE TABLE IF NOT EXISTS`. The API's own schema is untouched and stays
        with Alembic, where it has forty-five migrations that do need managing.
        """
        async with self._engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

    def _upsert(self, table: Table):
        """`ON CONFLICT DO UPDATE`, in whichever dialect this engine speaks.

        Postgres in production, SQLite in the tests. Both spell it the same way and neither
        spelling is the generic one, so the choice has to be made here.
        """
        return sqlite_insert(table) if self._engine.dialect.name == "sqlite" else (
            postgres_insert(table)
        )

    # ── Writing ───────────────────────────────────────────────────────────────

    async def append_entry(self, salon_id: str, entry: JournalEntry) -> None:
        statement = journal_table.insert().values(
            salon_id=salon_id,
            sequence=entry.sequence,
            participant_id=entry.participant_id,
            text=entry.text,
            language=entry.language,
            arrived_at=entry.arrived_at,
            duration_seconds=entry.duration_seconds,
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement)

    async def save_cursor(self, salon_id: str, interpreter_id: str, position: int) -> None:
        statement = self._upsert(cursor_table).values(
            salon_id=salon_id, reader_id=interpreter_id, position=position
        )
        statement = statement.on_conflict_do_update(
            index_elements=["salon_id", "reader_id"],
            set_={"position": statement.excluded.position},
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement)

    async def save_translation(
        self, salon_id: str, sequence: int, language: str, text: str
    ) -> None:
        # Nothing to update on conflict: the same pair always renders to the same text, and
        # two instances racing to write it are writing the same thing.
        statement = self._upsert(translation_table).values(
            salon_id=salon_id, sequence=sequence, language=language, text=text
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=["salon_id", "sequence", "language"]
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement)

    # ── Reading ───────────────────────────────────────────────────────────────

    async def load(self, salon_id: str) -> SalonState:
        """Read a Salon back, in one transaction.

        One transaction and not three: a takeover that read the journal, then the
        positions, then the translations could see a position pointing past the last
        message it had read, and would then render nothing at all.
        """
        async with self._engine.begin() as connection:
            entries = (
                await connection.execute(
                    select(journal_table)
                    .where(journal_table.c.salon_id == salon_id)
                    .order_by(journal_table.c.sequence)
                )
            ).all()
            cursors = (
                await connection.execute(
                    select(cursor_table.c.reader_id, cursor_table.c.position).where(
                        cursor_table.c.salon_id == salon_id
                    )
                )
            ).all()
            translations = (
                await connection.execute(
                    select(
                        translation_table.c.sequence,
                        translation_table.c.language,
                        translation_table.c.text,
                    ).where(translation_table.c.salon_id == salon_id)
                )
            ).all()

        return SalonState(
            entries=tuple(
                JournalEntry(
                    sequence=row.sequence,
                    participant_id=row.participant_id,
                    text=row.text,
                    language=row.language,
                    arrived_at=_as_utc(row.arrived_at),
                    duration_seconds=row.duration_seconds,
                )
                for row in entries
            ),
            cursors={row.reader_id: row.position for row in cursors},
            translations={(row.sequence, row.language): row.text for row in translations},
        )
