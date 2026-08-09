"""Rendering a message into another language, at most once, and always from the original.

Two rules do all the work. A translation is one hop from what was actually said, never a
translation of a translation; and the pair (message, language) is produced once however
many people ask for it. Together they make the cost of a Salon follow the number of
languages in it rather than the number of participants or the number of turns.
"""
import pytest

from src.journal import Journal, Translations

MORNING = dict(participant_id="hans", text="Guten Morgen", language="de")
BONJOUR = dict(participant_id="marie", text="Bonjour", language="fr")


class RecordingTranslator:
    """Records every call, so a test can assert what was asked of it — and mostly, that it
    was not asked anything at all."""

    def __init__(self):
        self.calls = []

    async def __call__(self, text: str, *, source: str, target: str) -> str:
        self.calls.append((text, source, target))
        return f"{text} [{source}->{target}]"


@pytest.fixture
def translator():
    return RecordingTranslator()


@pytest.fixture
def journal():
    return Journal(salon_id="salon-1")


@pytest.fixture
def translations(translator):
    return Translations(translate=translator)


async def test_a_message_is_rendered_into_the_language_asked_for(
    journal, translations, translator
):
    entry = journal.append(**MORNING)

    assert await translations.render(entry, "fr") == "Guten Morgen [de->fr]"
    assert translator.calls == [("Guten Morgen", "de", "fr")]


async def test_a_message_already_in_the_right_language_is_not_translated(
    journal, translations, translator
):
    """The original is rendered as it stands and no translation line is created. There is
    nothing to store, and storing a copy of the text under another name would be a claim
    about where it came from that is not true."""
    entry = journal.append(**BONJOUR)

    assert await translations.render(entry, "fr") == "Bonjour"
    assert translator.calls == []
    assert translations.cached(entry.sequence) == {}


async def test_a_regional_variant_is_still_the_same_language(
    journal, translations, translator
):
    """Somebody listening in fr-CA does not need a message spoken in fr translated, and
    paying to turn French into French would also risk it being quietly rephrased."""
    entry = journal.append(**BONJOUR)

    assert await translations.render(entry, "fr-CA") == "Bonjour"
    assert translator.calls == []


async def test_the_same_pair_is_produced_once(journal, translations, translator):
    """Three people listening in French share one translation — which is why the cache is
    keyed on the pair and not on the listener."""
    entry = journal.append(**MORNING)

    first = await translations.render(entry, "fr")
    second = await translations.render(entry, "fr")

    assert first == second
    assert len(translator.calls) == 1


async def test_different_languages_are_different_work(journal, translations, translator):
    entry = journal.append(**MORNING)

    await translations.render(entry, "fr")
    await translations.render(entry, "es")

    assert [call[2] for call in translator.calls] == ["fr", "es"]


async def test_every_translation_starts_from_the_original(journal, translations, translator):
    """Three speakers in three languages make three originals, and every rendering is one
    hop from the one it renders. A chain would compound its own errors, and the third
    listener would be told something the speaker never said."""
    entry = journal.append(**MORNING)

    for language in ("fr", "es", "it"):
        await translations.render(entry, language)

    assert {call[0] for call in translator.calls} == {"Guten Morgen"}
    assert {call[1] for call in translator.calls} == {"de"}


async def test_a_monolingual_salon_never_touches_the_translator(
    journal, translations, translator
):
    """The subsystem stays entirely idle. Cost and latency follow the linguistic variety of
    a Salon, never the volume of its conversation."""
    for _ in range(20):
        entry = journal.append(**BONJOUR)
        await translations.render(entry, "fr")

    assert translator.calls == []


async def test_a_cached_translation_is_readable_without_asking_again(journal, translations):
    entry = journal.append(**MORNING)
    await translations.render(entry, "fr")

    assert translations.cached(entry.sequence) == {"fr": "Guten Morgen [de->fr]"}


async def test_a_new_translation_is_announced_once(journal, translator):
    """What the Salon's log listens to in order to persist it. Announced on production and
    not on every read, or a popular language would be written to storage once per listener."""
    produced = []

    async def remember(sequence, language, text):
        produced.append((sequence, language, text))

    translations = Translations(translate=translator, on_new=remember)
    entry = journal.append(**MORNING)

    await translations.render(entry, "fr")
    await translations.render(entry, "fr")

    assert produced == [(1, "fr", "Guten Morgen [de->fr]")]


async def test_a_restored_cache_is_not_re_earned(journal, translator):
    """A takeover re-reads what was already translated. Paying for it again would make an
    instance failure cost money as well as an interruption."""
    translations = Translations(translate=translator, cache={(1, "fr"): "déjà fait"})
    entry = journal.append(**MORNING)

    assert await translations.render(entry, "fr") == "déjà fait"
    assert translator.calls == []


async def test_a_message_with_no_declared_language_is_left_to_the_translator(
    journal, translations, translator
):
    """The model does not always report one. The translator detects the source itself, so a
    missing value costs nothing — but it must not be guessed at here."""
    entry = journal.append(participant_id="x", text="Hola", language="")

    await translations.render(entry, "fr")

    assert translator.calls == [("Hola", "", "fr")]


async def test_an_empty_target_means_as_spoken(journal, translations, translator):
    """`caption_language = ""` is a choice in its own right — "as spoken, translate
    nothing" — and distinct from never having chosen."""
    entry = journal.append(**MORNING)

    assert await translations.render(entry, "") == "Guten Morgen"
    assert translator.calls == []
