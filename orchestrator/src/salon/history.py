"""Whether a late arrival is given what was said before they got here.

The host decides, in the same breath as the invitation — "invite Marie, with the history"
or "without". One utterance, one decision, because a second prompt at that moment is a
second thing to do while somebody is waiting to be let in.

Saying nothing is not a refusal. It falls to the default, which is a product decision
rather than a reading of what the host meant: somebody invited into a conversation is being
invited into what it has been about, and a host who wants otherwise has to say so.
"""
from __future__ import annotations

from enum import Enum

# `historique_arrivant_par_defaut`. True to start with, and a setting rather than a constant
# once Story 7.1 gives the operational parameters a table of their own.
DEFAULT_HISTORY_FOR_ARRIVALS = True


class HistoryAccess(Enum):
    """What the host said about the history when they invited somebody."""

    GRANTED = "granted"
    REFUSED = "refused"
    # They did not say. Distinct from a refusal, and it is the default that decides.
    UNSPECIFIED = "unspecified"


# What a refusal sounds like, and what a grant sounds like, in the languages a host is
# likely to be speaking. Refusals are checked first and that ordering is the whole
# subtlety: "sans l'historique" contains "l'historique", so matching the grant first would
# turn every refusal into permission — the one error here worth designing against.
_REFUSALS = (
    "sans l'historique",
    "sans historique",
    "without the history",
    "without history",
    "sin el historial",
    "sin historial",
    "ohne verlauf",
    "ohne den verlauf",
    "sem o histórico",
    "sem histórico",
    "senza lo storico",
    "senza storico",
)

_GRANTS = (
    "avec l'historique",
    "avec historique",
    "with the history",
    "with history",
    "con el historial",
    "mit verlauf",
    "mit dem verlauf",
    "com o histórico",
    "com histórico",
    "con lo storico",
    "con storico",
)


def history_from_invitation(said: str | None) -> HistoryAccess:
    """Read the host's decision out of what they actually said.

    Nothing recognised means nothing was decided, not that it was refused — the difference
    matters, because one of those is the host's choice and the other is ours.
    """
    spoken = (said or "").casefold()
    if not spoken:
        return HistoryAccess.UNSPECIFIED

    if any(phrase in spoken for phrase in _REFUSALS):
        return HistoryAccess.REFUSED
    if any(phrase in spoken for phrase in _GRANTS):
        return HistoryAccess.GRANTED

    return HistoryAccess.UNSPECIFIED


def grants_history(decision: HistoryAccess) -> bool:
    """Whether this decision ends up giving somebody the history."""
    if decision is HistoryAccess.UNSPECIFIED:
        return DEFAULT_HISTORY_FOR_ARRIVALS
    return decision is HistoryAccess.GRANTED
