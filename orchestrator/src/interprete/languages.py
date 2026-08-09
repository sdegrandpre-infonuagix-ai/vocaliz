"""Which languages the product offers, given adapters that do not agree.

One rule: the intersection of what the adapters speak, never their union.

It is a commercial decision before it is a technical one. A language only the Base adapter
speaks would work perfectly until the customer upgraded — and would then vanish, at the
exact moment they started paying more. Refusing it up front costs a language nobody had;
offering it costs a customer.

Speech-to-speech is the most restrictive of the adapters, so speech-to-speech decides. That
is an observation about today's models rather than a rule, and nothing here depends on it.
"""
from __future__ import annotations

from typing import Iterable


def base_language(language: str) -> str:
    """A language without its region. `fr-CA` and `fr-FR` are both French.

    Adapters list languages, not locales, and asking them to enumerate every region would
    produce lists that disagree for no reason.
    """
    return language.split("-")[0].strip().lower()


def offered_languages(*catalogues: Iterable[str]) -> frozenset[str]:
    """What every one of these adapters can speak.

    No adapters at all gives nothing, which is the deliberate answer: an empty intersection
    is conventionally everything, and everything is precisely the one result that would
    silently break the promise this function exists to keep.
    """
    if not catalogues:
        return frozenset()

    return frozenset.intersection(
        *(frozenset(base_language(language) for language in catalogue) for catalogue in catalogues)
    )
