"""Building a real Salon: the persisted journal, and rooms that exist on LiveKit.

Outside `src/` for the same reason `livekit_rooms.py` is — this is where the provider is
named, and the domain must not name one. `src/main.py` reaches for this once, in its
lifespan, and everything it hands the application afterwards is a plain callable.

What a Salon needs to exist is smaller than it looks: a journal it can write to, and
something that can open a room. It needs no interpreter at all, which is the whole of the
text-only boundary expressed as a constructor argument that is not there.
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy.ext.asyncio import create_async_engine

from adapters.livekit_rooms import LiveKitRoomProvisioner
from src.journal import SalonLog, SqlJournalStore
from src.journal.sql_store import async_url
from src.salon import Salon
from src.settings import SalonSettings


async def translation_not_wired(text: str, *, source: str, target: str) -> str:
    """Refuses, loudly, rather than handing back the original text.

    Captions (Story 6.14) are the only thing that translates in this process — every other
    translation happens inside an agent's interpreter, in the same movement as speaking. No
    text translator is wired yet, and the tempting placeholder is to return `text` unchanged.
    That would put German under a heading that says French, which a reader cannot detect and
    would trust. Raising means captions in another language fail visibly the first time
    somebody asks for them, which is the only honest failure available here.
    """
    raise NotImplementedError(
        "no text translator is wired: captions cannot be shown in a language "
        f"other than the one spoken (asked for {source!r} → {target!r})"
    )


async def build_salon_factory(
    *,
    database_url: str,
    livekit_url: str,
    livekit_api_key: str,
    livekit_api_secret: str,
    settings: SalonSettings | None = None,
) -> Callable[[str], Salon]:
    """A callable that turns a Salon identifier into a running Salon.

    Configuration in, a callable out. Opening the database and creating the journal's three
    tables happens here rather than in the lifespan, because they belong to this side of the
    boundary: `src/main.py` does not know that a Salon needs storage at all, and asking it to
    prepare some would be the domain knowing its adapter by another name.

    One store and one provisioner across every Salon this instance hosts. Neither holds a
    connection between calls — the store opens one per statement and the provisioner one per
    room — so sharing them costs nothing and saves building them per conversation.
    """
    engine = create_async_engine(async_url(database_url))
    store = SqlJournalStore(engine)
    await store.create_all()
    rooms = LiveKitRoomProvisioner(
        url=livekit_url, api_key=livekit_api_key, api_secret=livekit_api_secret
    )

    def build(salon_id: str) -> Salon:
        # A fresh journal rather than `SalonLog.resume`. Hosting is what the API calls when
        # it creates the Salon, so there is nothing to re-read; taking over a Salon already
        # under way is a different verb, and inventing it here would mean an empty journal
        # quietly overwriting a conversation in progress.
        log = SalonLog(salon_id=salon_id, store=store, translate=translation_not_wired)
        return Salon(log=log, rooms=rooms, settings=settings)

    return build
