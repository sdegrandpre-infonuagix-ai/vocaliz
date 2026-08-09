"""Cutting a long intervention into messages other people can get a word into.

The number is not the point. The journal is read in order, so one enormous message is a
stretch of time during which nobody else can be heard by anybody — a participant who talks
for two minutes without pausing would own the conversation for two minutes. Cutting the
intervention gives everyone else a position to land in.

Where the cut falls is the whole craft:

- a sentence boundary is where a listener expects a pause anyway, so the seam is inaudible;
- between words when a sentence is itself too long, which is the least bad place left;
- inside a word never, except for the single case of a word longer than the whole maximum,
  where the alternative is dropping it.
"""
from __future__ import annotations

import re

# `taille_max_message` of Story 6.5, and a setting rather than a constant once Story 7.1
# gives the operational parameters a table of their own.
MAX_MESSAGE_CHARACTERS = 500

# The end of a sentence: one terminator, optionally closing a quote or bracket, followed by
# whitespace. Requiring the whitespace is what keeps "3.5" one number and not two
# sentences — and the negative lookbehind keeps "..." one hesitation rather than three
# endings with two empty pieces between them.
_SENTENCE_END = re.compile(r"(?<![.!?…])[.!?…。！？]+[\"'»)\]]*(?=\s|$)")


def _sentences(text: str) -> list[str]:
    """Split on sentence boundaries, keeping the punctuation with the sentence it ends."""
    pieces: list[str] = []
    start = 0

    for match in _SENTENCE_END.finditer(text):
        sentence = text[start : match.end()].strip()
        if sentence:
            pieces.append(sentence)
        start = match.end()

    tail = text[start:].strip()
    if tail:
        pieces.append(tail)

    return pieces


def _by_words(sentence: str, max_chars: int) -> list[str]:
    """Cut a sentence that is itself too long, between words.

    A speaker who never punctuates still has to be cut somewhere. A word longer than the
    whole maximum — a URL read out, a compound in a language that does not space them — is
    cut through as a last resort: dropping it would lose what was said, and keeping it
    whole would break the promise that no message exceeds the maximum.
    """
    pieces: list[str] = []
    current = ""

    for word in sentence.split():
        while len(word) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(word[:max_chars])
            word = word[max_chars:]

        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current = f"{current} {word}"
        else:
            pieces.append(current)
            current = word

    if current:
        pieces.append(current)

    return pieces


def split_intervention(
    text: str, max_chars: int = MAX_MESSAGE_CHARACTERS
) -> tuple[str, ...]:
    """One intervention as the consecutive messages it will occupy in the journal.

    Greedy: as many whole sentences per piece as fit. Fewer and fuller pieces mean fewer
    seams for a listener to hear.

    Nothing is lost and nothing is invented — the words come out in the order they went in.
    """
    text = (text or "").strip()
    if not text:
        return ()
    if len(text) <= max_chars:
        return (text,)

    pieces: list[str] = []
    current = ""

    for sentence in _sentences(text):
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_by_words(sentence, max_chars))
            continue

        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current = f"{current} {sentence}"
        else:
            pieces.append(current)
            current = sentence

    if current:
        pieces.append(current)

    return tuple(pieces)
