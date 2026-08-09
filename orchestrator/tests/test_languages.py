"""Which languages the product offers, given adapters that do not agree.

One rule, and it is a commercial one before it is a technical one: the offered set is the
intersection of what the adapters speak, never their union. Speech-to-speech is the most
restrictive, so speech-to-speech decides.

The case that rule exists for: a language only the Base adapter speaks would work perfectly
until the customer upgraded, and would then vanish — at the exact moment they started paying
more. Refusing it up front costs a language nobody had; offering it costs a customer.
"""
from src.interprete import offered_languages

S2S = {"fr", "en", "es", "de"}
BASE = {"fr", "en", "es", "de", "cy", "is", "mt"}


def test_the_offer_is_what_every_adapter_speaks():
    assert offered_languages(S2S, BASE) == frozenset({"fr", "en", "es", "de"})


def test_a_language_only_one_adapter_speaks_is_not_offered():
    """Welsh, Icelandic and Maltese are real languages the Base stack handles. They are
    still refused, because they would disappear on an upgrade."""
    offered = offered_languages(S2S, BASE)

    assert "cy" not in offered
    assert offered.isdisjoint({"cy", "is", "mt"})


def test_the_most_restrictive_adapter_decides():
    assert offered_languages(S2S, BASE) == offered_languages(S2S, BASE, BASE) == frozenset(S2S)


def test_changing_tier_never_changes_the_languages():
    """The acceptance criterion, and it is a consequence rather than a rule of its own: the
    offer is a subset of every adapter, so every adapter can honour all of it."""
    offered = offered_languages(S2S, BASE)

    assert offered <= S2S
    assert offered <= BASE


def test_a_third_adapter_can_only_narrow_the_offer():
    """Whatever Story 6.7's successors bring, adding one never widens what is promised."""
    narrower = offered_languages(S2S, BASE, {"fr", "en"})

    assert narrower == frozenset({"fr", "en"})
    assert narrower <= offered_languages(S2S, BASE)


def test_adapters_with_nothing_in_common_offer_nothing():
    """Not a useful configuration, but it must read as an empty offer rather than as a
    crash or — far worse — as everything."""
    assert offered_languages({"fr"}, {"de"}) == frozenset()


def test_offering_nothing_at_all_is_not_offering_everything():
    """An empty argument list is a misconfiguration. Returning everything would be the one
    answer that silently breaks the promise this function exists to keep."""
    assert offered_languages() == frozenset()


def test_a_region_is_not_a_different_language():
    """Somebody set to fr-CA is offered French; the adapters do not list every region and
    should not have to."""
    assert offered_languages({"fr", "en"}, {"fr-CA", "en-GB", "cy"}) == frozenset({"fr", "en"})


def test_the_offer_is_named_in_its_base_form():
    assert all("-" not in language for language in offered_languages({"fr-CA"}, {"fr-FR"}))
