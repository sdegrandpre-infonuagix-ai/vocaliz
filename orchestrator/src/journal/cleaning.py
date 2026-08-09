"""Taking the hesitation out, and keeping the silences that were doing work.

Done once, at ingestion, and every listener benefits. The alternative — cleaning on the way
out — costs N times as much to arrive at the same journal, and would have to agree with
itself N times.

There is a line here and it is the whole difficulty: cleaning is not condensing (FR53).
Hesitation goes; not one word carrying meaning does. A cleaner that "tightens" a sentence
is paraphrasing somebody without telling them, and in a language the listener does not
speak they have no way of noticing.

A pause is the interesting case, because silence is not always nothing. Under
`SIGNIFICANT_PAUSE_MS` it is breathing and goes with the rest. Over it, it was carrying
something, so it survives as a marker: never pronounced, never injectable by saying it out
loud, not counted as content, and counted in full against a reader's lag — because it
occupies real time when it is restituted.
"""
from __future__ import annotations

import re

# `seuil_pause_signifiante`. Below this a silence is breathing. Two settings rather than one
# with a multiplier, because "what counts as meaningful" and "how long may we reproduce"
# are different questions — Story 7.1 gives both a row of their own.
SIGNIFICANT_PAUSE_MS = 2000

# `pause_max`. Thirty seconds of silence becomes five: reproducing it faithfully would mean
# reproducing the moment everybody assumed the call had dropped.
MAX_PAUSE_MS = 5000

# The metadata channel of the journal: `[key=value]`, never spoken, never counted as
# content. Story 6.11 promises later markers — emphasis, tone — take the same form and the
# same rules, so everything here is written against the shape rather than against `pause`.
MARKER = re.compile(r"\[([a-z_]+)=([^\]\s]*)\]")
PAUSE_MARKER = re.compile(r"\[pause=(\d+)\]")

# Hesitation, in the languages a Salon is likely to contain. Matched whole, with word
# boundaries: "heureux" begins with "heu", and deleting a word for looking like a noise is
# exactly the failure this module exists to avoid.
_FILLERS = (
    "euh", "heu", "hum", "hein", "ben", "eh",
    "um", "uh", "erm", "er", "hmm", "mmm",
    "ähm", "äh", "ehm",
    "este", "pues",
    "ecco", "cioè",
)
_FILLER = re.compile(
    r"(?<!\w)(?:" + "|".join(_FILLERS) + r")(?!\w)[\s,.…]*",
    re.IGNORECASE,
)

# An involuntary repetition: the same *short* word twice in a row. Short on purpose —
# people stammer on function words ("je je pense", "the the thing"), and repeating a longer
# one is usually deliberate: "très très bien" means something "très bien" does not.
#
# The asymmetry decides where to draw it. Missing a stammer costs a listener one repeated
# syllable; deleting a word somebody meant costs them a meaning, in a language they have no
# way of checking.
_STAMMER_MAX_LETTERS = 3
_STAMMER = re.compile(
    rf"(?<!\w)(\w{{1,{_STAMMER_MAX_LETTERS}}})(\s+\1)+(?!\w)", re.IGNORECASE
)

_SPACES = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?…])")


def pause_marker(milliseconds: int) -> str:
    """The marker for a silence, or nothing when it was only breathing."""
    if milliseconds <= SIGNIFICANT_PAUSE_MS:
        return ""
    return f"[pause={min(milliseconds, MAX_PAUSE_MS)}]"


def pause_seconds(text: str) -> float:
    """How long the silences in a message take to restitute.

    They count in full against a reader who has not reached them yet: a pause occupies real
    time when it is played, and pretending otherwise would understate every lag behind it.
    """
    return sum(int(ms) for ms in PAUSE_MARKER.findall(text or "")) / 1000.0


def without_markers(text: str) -> str:
    """The words alone. What a condensation gets (FR53): one does not summarise silences."""
    return _tidy(MARKER.sub(" ", text or ""))


def spoken_length(text: str) -> int:
    """How much of a message is speech.

    What Story 6.5 measures against `taille_max_message`. A marker is not speech, and
    counting it would cut interventions short for a reason nobody could hear.
    """
    return len(without_markers(text))


def neutralise(text: str) -> str:
    """Defang anything marker-shaped that came out of a human's mouth.

    A participant reading "[pause=4000]" aloud is a participant saying words. Letting that
    become metadata would let anybody put silence into anybody else's ears — and the same
    hole would open for every marker added later, which is why this matches the shape and
    not the word `pause`.
    """
    return MARKER.sub(lambda m: f"({m.group(1)} {m.group(2)})", text or "")


def clean(text: str | None, *, keep_markers: bool = False) -> str:
    """Remove hesitation and involuntary repetition, and nothing else.

    `keep_markers` is for the adapter that has just inserted its own pause markers: it
    trusts them, and everything from outside is neutralised first regardless.
    """
    if not text:
        return ""

    if keep_markers:
        held: list[str] = []

        def hold(match: re.Match[str]) -> str:
            held.append(match.group(0))
            return f"\x00{len(held) - 1}\x00"

        text = PAUSE_MARKER.sub(hold, text)
        text = neutralise(text)
    else:
        held = []
        text = neutralise(text)

    text = _FILLER.sub(" ", text)
    text = _STAMMER.sub(r"\1", text)
    text = _tidy(text)

    for index, marker in enumerate(held):
        text = text.replace(f"\x00{index}\x00", marker)

    return _tidy(text)


def _tidy(text: str) -> str:
    """Collapse what removing a word left behind, without moving anything that remains."""
    text = _SPACES.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    return text.strip(" ,;:")
