"""What a telephone guest hears first, and what the host hears when nobody answers (Story 10.5).

Dialling out cannot be built here — there is no SIP trunk — but two of the story's criteria are
about words rather than about telephony, and they are the two that decide whether the feature is
usable or alarming.

**The person who picks up did not ask for this.** Their telephone rang, an unfamiliar voice
speaks, and unless the first sentence says who is calling and why, the reasonable response is to
hang up. So the interpreter names the host, says it is interpreting, and says it in one
sentence — somebody deciding whether to stay on the line is not listening to a paragraph.

**The host is in a conversation, not looking at a screen.** A call that quietly fails to connect
leaves them waiting for somebody who is never coming, so every outcome is spoken: no answer,
declined, hung up. NFR3, applied to the one participant whose absence nobody else can see.

Both live beside the other notices, written per language rather than translated at runtime: they
are said at the exact moment the interpreter is not yet interpreting for this person, and there
is no detected language to translate into yet.
"""
import pytest

from src.salon.notices import (
    call_declined,
    call_not_answered,
    caller_hung_up,
    telephone_greeting,
)

LANGUAGES = ("fr", "en", "es", "de", "pt", "it")


# ── The first thing a telephone guest hears ───────────────────────────────────


def test_it_names_the_host(pytestconfig=None):
    """Never "somebody has invited you". A name is what turns a strange call into an
    expected one, and it is the whole reason the sentence exists."""
    assert "Marie" in telephone_greeting("Marie", told_in="en")


def test_it_says_what_is_about_to_happen(pytestconfig=None):
    """One sentence about interpretation. Somebody deciding whether to stay on the line is
    not listening to a paragraph."""
    said = telephone_greeting("Marie", told_in="en").lower()

    assert "interpret" in said


def test_it_is_one_sentence(pytestconfig=None):
    """Counted rather than intended. Two sentences is where an explanation starts growing."""
    said = telephone_greeting("Marie", told_in="en")

    assert said.count(".") == 1


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_language_greets_and_names(language):
    said = telephone_greeting("Marie", told_in=language)

    assert "Marie" in said
    assert said.endswith(".")


def test_an_unknown_language_still_says_something(pytestconfig=None):
    """A greeting in the wrong language still tells somebody a human is behind this call.
    Silence tells them it is a machine, and they hang up."""
    assert "Marie" in telephone_greeting("Marie", told_in="cy")


def test_a_host_with_no_name_is_not_invented(pytestconfig=None):
    """Some hosts are known only by an address, which is not a name and must never be read
    out to a stranger. The sentence stays truthful and says somebody rather than nobody."""
    said = telephone_greeting(None, told_in="en")

    assert "@" not in said
    assert said.endswith(".")


def test_a_host_address_is_never_read_aloud(pytestconfig=None):
    """The one leak this sentence could produce. Whoever answers is a stranger to the host
    until they choose otherwise."""
    said = telephone_greeting("marie@example.com", told_in="en")

    assert "marie@example.com" not in said


# ── What the host is told when it does not work ───────────────────────────────


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_answer_is_spoken_in_every_language(language):
    assert call_not_answered(told_in=language).endswith(".")


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_refusal_is_spoken_in_every_language(language):
    assert call_declined(told_in=language).endswith(".")


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_hang_up_is_spoken_in_every_language(language):
    assert caller_hung_up(told_in=language).endswith(".")


def test_the_three_outcomes_are_distinguishable(pytestconfig=None):
    """No answer, declined and hung up are three different things to a host deciding whether
    to try again. One sentence for all three would make the feature unusable."""
    said = {
        call_not_answered(told_in="en"),
        call_declined(told_in="en"),
        caller_hung_up(told_in="en"),
    }

    assert len(said) == 3


def test_none_of_them_says_the_salon_is_over(pytestconfig=None):
    """The Salon carries on. A notice that sounded like an ending would end a conversation
    that was fine."""
    for said in (
        call_not_answered(told_in="en"),
        call_declined(told_in="en"),
        caller_hung_up(told_in="en"),
    ):
        assert "ended" not in said.lower()
        assert "over" not in said.lower()


def test_a_number_is_never_read_back_in_a_failure(pytestconfig=None):
    """The host already knows which number they asked for, and the others in the room do not
    need it. These are spoken into a room with people in it."""
    for said in (
        call_not_answered(told_in="en"),
        call_declined(told_in="en"),
        caller_hung_up(told_in="en"),
    ):
        assert not any(character.isdigit() for character in said)
