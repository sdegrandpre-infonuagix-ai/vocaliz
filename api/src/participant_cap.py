"""How many people fit in a Salon, and who decides (Story 10.2, replacing FR2).

Three is a starting value and never a fact about the product. The multi-rooms topology gives
each participant their own room and their own interpreter, so nothing in it counts to three or
to any other number: a fourth person costs one more interpreter, which is a price question
rather than an architectural one. Build for N, configure at 3.

Which is why the ceiling moved out of the environment and into the persisted settings of Story
7.1. It is a number somebody will want to raise for one customer, on a Tuesday, and a knob
behind a deployment is a knob that in practice never gets turned. The API reads the same
`salon_settings` table the orchestrator writes — one table, two readers, and no second copy to
disagree with the first.

Read per call rather than at import. A value changed while the service is running has to be the
value the next Salon gets, which is the whole of what "without a redeploy" means.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# The name the orchestrator's `DEFAULTS` uses. One spelling, in both codebases, because the
# row is written by one and read by the other.
CEILING_SETTING = "participant_ceiling"

# What applies until somebody stores something else. Documented rather than absent: the
# settings table holds only what was actually changed, so a missing row means "nobody has
# moved this" and not "nothing is configured".
DEFAULT_CEILING = 3

# One participant and their interpreter is somebody talking to a translation of themselves.
MINIMUM_CAP = 2


def ceiling(db: Session) -> int:
    """The largest Salon this deployment allows, from the persisted settings.

    Falls back to `DEFAULT_CEILING` when the row is absent — and when the table is not there
    at all, which is the state of a deployment whose orchestrator has never started. Failing
    to create Salons because a tuning table is missing would be an outage caused by a knob.
    """
    try:
        row = db.execute(
            text("SELECT value FROM salon_settings WHERE name = :name"),
            {"name": CEILING_SETTING},
        ).first()
    except Exception:  # noqa: BLE001
        logger.warning("Could not read %s; using the default", CEILING_SETTING, exc_info=True)
        db.rollback()
        return DEFAULT_CEILING

    if row is None or row[0] is None:
        return DEFAULT_CEILING
    # One numeric column serves every parameter, so a whole number of people arrives as a
    # float. Half a participant is not something to provision a room for.
    return int(row[0])


def bounded(requested: int | None, *, ceiling: int) -> int:
    """What a host actually gets, given what they asked for.

    Asking for more than the ceiling is **bounded rather than refused**: they asked for the
    biggest Salon available and the biggest available is what they get. A refusal would send
    somebody hunting for a number nobody published.

    Saying nothing is the offer, not a Salon for nobody.

    The floor wins over a ceiling set below it. `SalonSettings` refuses to store such a
    ceiling, so this only fires on a row written by hand — and the alternative is returning a
    number the `salons` CHECK cannot store, which would turn a bad setting into a 500 on
    every attempt to open a Salon.
    """
    if requested is None:
        return max(MINIMUM_CAP, ceiling)
    return max(MINIMUM_CAP, min(ceiling, requested))


def is_full(present: int, *, cap: int) -> bool:
    """Whether one more person can be let in.

    `>=` rather than `==`: a cap lowered under a Salon that is already above it would
    otherwise read as room to spare, and everybody would be let in.
    """
    return present >= cap


def room_full_message(*, cap: int) -> str:
    """Why somebody is not being let in, in terms they can act on.

    Carries the number. "The room is full" leaves somebody wondering whether to wait a
    moment; knowing the size tells them this is not a queue.
    """
    return (
        f"This Salon is full. It was opened for {cap} "
        f"{'person' if cap == 1 else 'people'}."
    )
