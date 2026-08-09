"""Reading the conversation while you hear it.

Captions are not a lesser copy of the voice — they reach further. Text renders into
languages no realtime model can pronounce, so somebody can follow a Salon in a language
they could never be spoken to in. That asymmetry is the feature rather than an accident of
implementation: the spoken set is the intersection of the adapters (Story 6.7), and the
readable set is deliberately wider.

Three states, and the middle one is the one that is easy to lose:

- `None` — never chosen. Captions are off because nobody has said anything about them.
- `""` (`AS_SPOKEN`) — chosen: show the original, translate nothing. A decision somebody
  made, and not the same as never having decided.
- a language — chosen: render every turn into it.
"""
from __future__ import annotations

from src.interprete.languages import base_language, offered_languages

# `caption_language = ""`. Distinct from NULL, which means "never chosen" — the difference
# between somebody who wants the original and somebody the question was never put to.
AS_SPOKEN = ""

# `caption_scale`. Follows the account rather than the device: somebody who needs larger
# text needs it on their telephone as well as on their laptop.
DEFAULT_CAPTION_SCALE = 1.0

# What each adapter can speak. The intersection of these is what the product offers to say
# out loud; nothing here widens it.
S2S_LANGUAGES = frozenset({"fr", "en", "es", "de", "pt", "it"})
BASE_LANGUAGES = frozenset({"fr", "en", "es", "de", "pt", "it", "cy", "is", "mt", "ga"})

# What can be *read*. A superset on purpose, and the reason the feature exists: rendering
# text into Welsh is a solved problem, and pronouncing it is not.
READABLE = BASE_LANGUAGES | {"nl", "pl", "sv", "da", "no", "fi", "cs", "el", "ro", "hu"}


def caption_languages() -> frozenset[str]:
    """Everything somebody may choose to read in."""
    return frozenset(base_language(language) for language in READABLE)


def captions_offered_in() -> frozenset[str]:
    """Everything the product will say out loud — the intersection, unchanged by any of this.

    Kept here beside the wider set so the two are read together: being able to read Welsh is
    not being able to be spoken to in it, and a participant reading a language no adapter
    speaks has their voice fall back while their captions do not.
    """
    return offered_languages(S2S_LANGUAGES, BASE_LANGUAGES)


def reads_captions(language: str | None) -> bool:
    """Whether a choice has been made at all. `""` is a choice; `None` is not."""
    return language is not None
