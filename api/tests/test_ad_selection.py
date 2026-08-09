"""Which advertisement an interpreter reads to its own participant (FR39 / FR50).

The exchange itself is inherited and untouched: the auction, the billing and the proof of
delivery all stay exactly as they were. What the multi-rooms topology changes is where an
advertisement *goes* — into one participant's room, read by their interpreter, in their
language. That is the only structural change this subsystem is asked to absorb, and this
module is it.

Selection is a **pull**. The interpreter asks when it has a gap; nothing is ever pushed at a
participant. That falls out of the topology rather than being a design preference — there is
no shared room to push into.

Two targeting criteria and no more: the cell somebody is in and the language they speak.
`ads.topic` stays deliberately unwired — choosing advertising from what a conversation is
about is a different kind of consent from keeping the words in order to translate them, and
nobody has been asked for it.

Cells are compared as strings at six digits on both sides. A mismatch of precision therefore
matches nothing rather than raising: an advertiser who supplied a finer code reaches nobody,
which is visible in their delivery count, whereas a silent coercion would put their money
somewhere they did not choose.
"""
import uuid
from datetime import datetime, timedelta, timezone

from src.ad_selection import CELL_DIGITS, Advertisement, choose_ad, rendered_text

NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _ad(name, *, cells=("87G8Q2",), languages=("en",), pitch=None,
        spoken_language="en", substitutions=None, seconds=0):
    """One advertisement, as selection sees it — the same value `inventory()` produces.

    Empty on a dimension means unrestricted there; empty on both is what makes an
    advertisement generic, which is why no test sets that flag by hand.
    """
    return Advertisement(
        id=uuid.uuid4(),
        cells=frozenset(cells),
        languages=frozenset(languages),
        sales_pitch=pitch or f"{name} is worth your time.",
        spoken_language=spoken_language,
        substitutions=substitutions or {},
        indicative_seconds=seconds,
    )


# ── Two criteria, and only two ────────────────────────────────────────────────


def test_an_ad_matching_the_cell_and_the_language_is_chosen():
    here = _ad("here", cells=("87G8Q2",), languages=("fr",))

    chosen = choose_ad([here], cell="87G8Q2", language="fr", heard={})

    assert chosen is here


def test_an_ad_for_another_cell_is_not_chosen():
    elsewhere = _ad("elsewhere", cells=("9C3XGV",), languages=("fr",))

    assert choose_ad([elsewhere], cell="87G8Q2", language="fr", heard={}) is None


def test_an_ad_in_another_language_is_not_chosen():
    """Target languages are a *targeting* criterion — the languages of the people it will be
    read to — rather than a property of the text, which is translated anyway."""
    wrong = _ad("wrong", cells=("87G8Q2",), languages=("de",))

    assert choose_ad([wrong], cell="87G8Q2", language="fr", heard={}) is None


def test_one_ad_can_address_several_cells_and_languages():
    """Without duplicating a row per combination, which is how an inventory table becomes
    unmaintainable."""
    broad = _ad("broad", cells=("87G8Q2", "9C3XGV"), languages=("fr", "de"))

    assert choose_ad([broad], cell="9C3XGV", language="de", heard={}) is broad


def test_the_topic_is_never_consulted():
    """Choosing advertising from what a conversation is about is a different kind of consent
    from keeping the words in order to translate them, and nobody has been asked for it."""
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[1] / "src" / "ad_selection.py"
    ).read_text(encoding="utf-8")
    code = source.split('"""', 2)[-1]

    assert "topic" not in code


# ── Cells are strings, at six digits both sides ───────────────────────────────


def test_a_cell_is_six_digits():
    assert CELL_DIGITS == 6


def test_a_finer_code_on_the_ad_matches_nothing_rather_than_being_coerced():
    """The advertiser reaches nobody and can see it in their delivery count. A silent
    truncation would put their money somewhere they did not choose."""
    precise = _ad("precise", cells=("87G8Q2XV+2C",), languages=("fr",))

    assert choose_ad([precise], cell="87G8Q2", language="fr", heard={}) is None


def test_a_finer_cell_from_the_participant_matches_nothing_either():
    coarse = _ad("coarse", cells=("87G8Q2",), languages=("fr",))

    assert choose_ad([coarse], cell="87G8Q2XV+2C", language="fr", heard={}) is None


def test_the_comparison_is_exact_rather_than_by_prefix():
    """Neighbouring cells are not near each other in any sense the string knows about."""
    neighbour = _ad("neighbour", cells=("87G8Q3",), languages=("fr",))

    assert choose_ad([neighbour], cell="87G8Q2", language="fr", heard={}) is None


def test_a_participant_with_no_cell_still_gets_something():
    """Somebody who refused geolocation (Story 9.1). They hear untargeted advertising, never
    silence."""
    generic = _ad("generic", cells=(), languages=())
    local = _ad("local", cells=("87G8Q2",), languages=("fr",))

    assert choose_ad([generic, local], cell="", language="fr", heard={}) is generic


def test_an_ad_naming_no_cell_reaches_every_cell():
    """Empty means unrestricted on that dimension, as it already does for an advertiser's
    lists. Anything else leaves a language-only campaign matching nobody at all."""
    anywhere = _ad("anywhere", cells=(), languages=("fr",))

    assert choose_ad([anywhere], cell="87G8Q2", language="fr", heard={}) is anywhere


def test_an_ad_naming_no_language_reaches_every_language():
    local = _ad("local", cells=("87G8Q2",), languages=())

    assert choose_ad([local], cell="87G8Q2", language="de", heard={}) is local


# ── Nothing heard twice while anything is unheard ─────────────────────────────


def test_an_unheard_ad_is_preferred():
    old = _ad("old", languages=("fr",))
    fresh = _ad("fresh", languages=("fr",))

    chosen = choose_ad([old, fresh], cell="87G8Q2", language="fr", heard={old.id: NOW})

    assert chosen is fresh


def test_everything_heard_is_replayed_oldest_first():
    """The inventory never runs out. Advertising silence is not an available outcome, so a
    small inventory cycles rather than stopping."""
    first = _ad("first", languages=("fr",))
    second = _ad("second", languages=("fr",))
    heard = {first.id: NOW - timedelta(hours=2), second.id: NOW}

    assert choose_ad([first, second], cell="87G8Q2", language="fr", heard=heard) is first


def test_replaying_does_not_change_the_frequency():
    """The cycle restarts; it does not accelerate. Frequency belongs to the tier (FR33), and
    this function is asked once per slot whatever the inventory looks like."""
    only = _ad("only", languages=("fr",))
    heard = {only.id: NOW}

    assert choose_ad([only], cell="87G8Q2", language="fr", heard=heard) is only


def test_the_choice_is_settled_when_two_were_heard_at_the_same_moment():
    """Two identical timestamps need a tie-break that does not vary between runs."""
    first = _ad("first", languages=("fr",))
    second = _ad("second", languages=("fr",))
    heard = {first.id: NOW, second.id: NOW}

    once = choose_ad([first, second], cell="87G8Q2", language="fr", heard=heard)
    twice = choose_ad([first, second], cell="87G8Q2", language="fr", heard=heard)

    assert once is twice


# ── Never silence ─────────────────────────────────────────────────────────────


def test_a_generic_ad_is_served_when_nothing_matches():
    """Rather than a silence or an error. The slot exists because the tier sells it."""
    generic = _ad("generic", cells=(), languages=())
    elsewhere = _ad("elsewhere", cells=("9C3XGV",), languages=("de",))

    assert choose_ad([generic, elsewhere], cell="87G8Q2", language="fr", heard={}) is generic


def test_a_targeted_ad_beats_a_generic_one():
    generic = _ad("generic", cells=(), languages=())
    local = _ad("local", cells=("87G8Q2",), languages=("fr",))

    assert choose_ad([generic, local], cell="87G8Q2", language="fr", heard={}) is local


def test_an_empty_inventory_returns_nothing_rather_than_raising():
    """There is no advertisement to read, which the caller handles by saying nothing. An
    exception here would take down a Salon over an empty table."""
    assert choose_ad([], cell="87G8Q2", language="fr", heard={}) is None


# ── What gets read out ────────────────────────────────────────────────────────


def test_the_creative_is_translated_like_any_other_content():
    """A text with derived translations, exactly as a turn is — never a pre-recorded file,
    which could not reach a language the advertiser did not anticipate."""
    ad = _ad("ad", pitch="Buy our bread", spoken_language="en")

    text, verbatim = rendered_text(ad, language="fr")

    assert text == "Buy our bread"
    assert verbatim is False


def test_a_substitution_is_read_word_for_word():
    """Brand wording or a legal order. Being read exactly is the whole of what a substitution
    guarantees."""
    ad = _ad("ad", pitch="Buy our bread", substitutions={"fr": "Achetez notre pain."})

    text, verbatim = rendered_text(ad, language="fr")

    assert text == "Achetez notre pain."
    assert verbatim is True


def test_a_substitution_applies_only_to_its_own_language():
    """The others keep being translated from the canonical creative."""
    ad = _ad("ad", pitch="Buy our bread", substitutions={"fr": "Achetez notre pain."})

    text, verbatim = rendered_text(ad, language="de")

    assert text == "Buy our bread"
    assert verbatim is False


def test_a_verbatim_text_is_exempt_from_every_interpretation_step():
    """No disfluency cleaning, no condensation, no shortening for lag. All three would change
    wording that was supplied precisely because it must not change."""
    ad = _ad("ad", substitutions={"fr": "Euh, achetez  notre pain."})

    text, verbatim = rendered_text(ad, language="fr")

    assert verbatim is True
    assert text == "Euh, achetez  notre pain."


def test_the_language_of_the_creative_needs_no_translation():
    ad = _ad("ad", pitch="Buy our bread", spoken_language="en")

    text, verbatim = rendered_text(ad, language="en")

    assert text == "Buy our bread"
    assert verbatim is False
