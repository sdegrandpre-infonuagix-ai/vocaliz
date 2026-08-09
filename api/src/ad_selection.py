"""Which advertisement an interpreter reads to its own participant (FR39 / FR50).

The exchange itself is inherited and untouched — the auction, the billing and the proof of
delivery all stay as they were. What the multi-rooms topology changes is where an
advertisement *goes*: into one participant's room, read by their interpreter, in their
language. That is the only structural change this subsystem absorbs, and this module is it.

Selection is a **pull**. The interpreter asks when it has a gap; nothing is pushed at anybody.
That follows from the topology rather than from taste — there is no shared room to push into.

Two targeting criteria and no more: the cell somebody is in, and the language they speak.
`ads.topic` stays unwired, and a test greps this file to keep it that way. Choosing
advertising from what a conversation is *about* is a different kind of consent from keeping
the words in order to translate them, and nobody has been asked for it.

Cells are compared as strings at six digits on both sides. A precision mismatch therefore
matches nothing rather than raising or being coerced: an advertiser who supplied a finer code
reaches nobody and can see it in their delivery count, whereas a silent truncation would put
their money somewhere they never chose.

Selection never holds an ORM row. `inventory()` reads the tables once and hands over plain
frozen values, so a Salon can choose between advertisements without a detached instance
lazy-loading a relationship in the middle of a conversation.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

# Borrowed as a database-time helper and nothing to do with money: SQLite has no timezone
# type and hands a stamped instant back naive, and comparing naive to aware raises. Copying
# the two lines here is how the two copies would drift.
from src.ledger import as_utc
from src.models.ad import Ad, AdLanguage, AdRegion, AdSubstitution
from src.models.ad_broadcast import AdBroadcast

# Six digits of Open Location Code, about 5.5 km — the same cell the consent story stores.
CELL_DIGITS = 6


@dataclass(frozen=True)
class Advertisement:
    """One advertisement, as selection sees it. Everything it needs, and nothing more."""

    id: uuid.UUID
    # Empty means unrestricted on that dimension, as an advertiser's empty list already
    # does. Anything else would leave a language-only campaign matching nobody at all.
    cells: frozenset[str] = frozenset()
    languages: frozenset[str] = frozenset()
    sales_pitch: str = ""
    spoken_language: str = "en"
    substitutions: dict[str, str] = field(default_factory=dict)
    # Indicative and never contractual: what counts in an interpreter's lag is the duration
    # actually rendered, which differs by language for one and the same text.
    indicative_seconds: int = 0

    @property
    def generic(self) -> bool:
        """Unrestricted on both dimensions — which is the whole of what generic means.

        Derived rather than stored, so an advertisement cannot claim to be generic while
        carrying targeting, or carry none while claiming not to be.
        """
        return not self.cells and not self.languages


def _targets(ad: Advertisement, *, cell: str, language: str) -> bool:
    """Whether this advertisement is aimed at this person.

    Exact string equality on the cell. Neighbouring cells are not near each other in any
    sense a string knows about, and a prefix match would quietly widen every campaign.
    """
    if ad.languages and language not in ad.languages:
        return False
    if ad.cells and cell not in ad.cells:
        return False
    return True


def choose_ad(
    inventory: Iterable[Advertisement],
    *,
    cell: str,
    language: str,
    heard: dict[uuid.UUID, datetime],
) -> Advertisement | None:
    """Pick one advertisement for one participant, or `None` if there are none at all.

    Targeted first, generic only as a fallback — a slot exists because the tier sells it, so
    silence is never the answer while any advertisement remains. `None` means the inventory
    is genuinely empty, which the caller handles by saying nothing; raising here would take a
    Salon down over an empty table.

    Among the candidates, anything unheard comes before anything heard, and heard ones return
    oldest-first. The inventory therefore cycles rather than running out, and the cycle
    restarts without accelerating: frequency belongs to the tier, and this is asked once per
    slot whatever the inventory looks like.
    """
    everything = list(inventory)
    candidates = [
        ad
        for ad in everything
        if not ad.generic and _targets(ad, cell=cell, language=language)
    ]
    if not candidates:
        candidates = [ad for ad in everything if ad.generic]
    if not candidates:
        return None

    def order(ad: Advertisement) -> tuple:
        when = heard.get(ad.id)
        # Unheard first; then oldest heard. The identifier breaks a tie between two heard at
        # the same instant, so the choice does not vary between runs.
        return (when is not None, when or datetime.min, str(ad.id))

    return sorted(candidates, key=order)[0]


def rendered_text(ad: Advertisement, *, language: str) -> tuple[str, bool]:
    """The words to say, and whether they must be said exactly as given.

    The creative is a text with derived translations, exactly as a turn is — never a
    pre-recorded file, which could not reach a language the advertiser did not anticipate.

    A substitution replaces it for **one** language only, the others carrying on from the
    canonical creative. When one applies, the second return value is `True` and no
    interpretation step may touch the words: no disfluency cleaning, no condensation, no
    shortening for lag. All three would alter wording supplied precisely because it must not
    be altered.
    """
    substitute = ad.substitutions.get(language)
    if substitute is not None:
        return substitute, True
    return ad.sales_pitch, False


def inventory(db: Session) -> list[Advertisement]:
    """Everything an interpreter may currently draw from.

    Exhausted advertisements are left out: zero broadcasts remaining is one that has done
    what it was paid for, and the row survives only so the history does.

    Read whole, in four queries rather than one per advertisement. An inventory is small and
    a Salon asks for it repeatedly; the shape that matters is that nothing here goes back to
    the database once the values are handed over.
    """
    ads = db.query(Ad).filter(Ad.number_of_broadcasts_left > 0).all()
    live = {row.ad_id for row in ads}

    cells: dict[uuid.UUID, set[str]] = {}
    for row in db.query(AdRegion).all():
        if row.ad_id in live:
            cells.setdefault(row.ad_id, set()).add(row.google_plus_code)

    languages: dict[uuid.UUID, set[str]] = {}
    for row in db.query(AdLanguage).all():
        if row.ad_id in live:
            languages.setdefault(row.ad_id, set()).add(row.language)

    substitutions: dict[uuid.UUID, dict[str, str]] = {}
    for row in db.query(AdSubstitution).all():
        if row.ad_id in live:
            substitutions.setdefault(row.ad_id, {})[row.language] = row.text

    return [
        Advertisement(
            id=row.ad_id,
            cells=frozenset(cells.get(row.ad_id, ())),
            languages=frozenset(languages.get(row.ad_id, ())),
            sales_pitch=row.sales_pitch,
            spoken_language=row.spoken_language,
            substitutions=substitutions.get(row.ad_id, {}),
            indicative_seconds=row.indicative_seconds,
        )
        for row in ads
    ]


def heard_in_salon(db: Session, salon_id: uuid.UUID) -> dict[uuid.UUID, datetime]:
    """When each advertisement was last actually spoken here.

    Delivered broadcasts only. `ad_broadcasts` deliberately distinguishes reserved from
    heard, and the same distinction that stops an advertiser being charged for a sentence
    nobody heard stops a participant being spared one they never got.

    The **last** delivery of each, not the first: replay order is oldest-heard first, so an
    advertisement heard twice should be as fresh as its most recent airing.
    """
    last: dict[uuid.UUID, datetime] = {}
    rows = (
        db.query(AdBroadcast)
        .filter(AdBroadcast.salon_id == salon_id, AdBroadcast.delivered_at.isnot(None))
        .all()
    )
    for row in rows:
        when = as_utc(row.delivered_at)
        if row.ad_id not in last or when > last[row.ad_id]:
            last[row.ad_id] = when
    return last
