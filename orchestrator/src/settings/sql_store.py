"""The durable side of `SettingsStore`.

One table, and it is a key/value one rather than a row of typed columns. That is the less
obvious choice and it is deliberate: adding a parameter to `DEFAULTS` should not require a
migration, and a table whose shape follows the dataclass would make every new knob a schema
change. The cost is that types live in `SalonSettings` rather than in the column, which is
where they were going to have to be checked anyway — the ordering rules are between fields,
and no column type can express those.

A name the dataclass does not know is refused on the way out rather than dropped, so a row
left behind by a removed parameter is loud instead of invisible.
"""
from __future__ import annotations

from typing import Mapping

from sqlalchemy import Column, Float, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine

metadata = MetaData()

# Every parameter is a duration or a length, so one numeric column serves them all. The
# integers among them are whole numbers stored as floats and handed back as floats; the
# dataclass is what decides that `max_message_characters` is an int, and it is the only
# place that should decide it.
settings_table = Table(
    "salon_settings",
    metadata,
    Column("name", String(64), primary_key=True),
    Column("value", Float, nullable=False),
)


class SqlSettingsStore:
    """`SettingsStore` over SQLAlchemy Core. Postgres in production, SQLite in the tests."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create_all(self) -> None:
        async with self._engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

    async def load(self) -> Mapping[str, float | int]:
        """Read every stored parameter.

        A missing row is not an error: it means nobody has moved that one, and the
        documented starting value applies. Only what has actually been changed is stored,
        which also makes the table readable — what is in it is what somebody decided.
        """
        async with self._engine.begin() as connection:
            rows = await connection.execute(select(settings_table.c.name, settings_table.c.value))
            return {name: value for name, value in rows.all()}

    async def save(self, values: Mapping[str, float | int]) -> None:
        if not values:
            return

        insert = sqlite_insert if self._engine.dialect.name == "sqlite" else postgres_insert
        async with self._engine.begin() as connection:
            for name, value in values.items():
                statement = insert(settings_table).values(name=name, value=float(value))
                await connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=[settings_table.c.name],
                        set_={"value": statement.excluded.value},
                    )
                )
