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
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Protocol

# Six digits of Open Location Code, about 5.5 km — the same cell the consent story stores.
CELL_DIGITS = 6


class Advertisement(Protocol):
    """What selection needs of an advertisement, and nothing more."""

    id: object
    cells: set[str]
    languages: set[str]
    sales_pitch: str
    spoken_language: str
    substitutions: dict[str, str]
    generic: bool


def _targets(ad: Advertisement, *, cell: str, language: str) -> bool:
    """Whether this advertisement is aimed at this person.

    Exact string equality on the cell. Neighbouring cells are not near each other in any
    sense a string knows about, and a prefix match would quietly widen every campaign.
    """
    if language not in ad.languages:
        return False
    return bool(cell) and cell in ad.cells


def choose_ad(
    inventory: Iterable[Advertisement],
    *,
    cell: str,
    language: str,
    heard: dict[object, datetime],
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
    candidates = [ad for ad in everything if _targets(ad, cell=cell, language=language)]
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
