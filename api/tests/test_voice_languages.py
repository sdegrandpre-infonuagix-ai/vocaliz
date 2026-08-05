"""The languages the voice model speaks, exactly as its documentation lists them.

Frozen as data because it was lost twice. The list is not derivable from anything in the
codebase — the seventy interface languages come from Amazon Translate and are about reading,
not speaking — so a version invented from memory would look plausible and offer callers a
voice the model cannot produce.

Source: docs.x.ai/developers/model-capabilities/audio/speech-to-speech, which is the page
for what the agent runs. Persian is the one entry that comes from testing instead.
"""
from src.services.voice_languages import (
    DOCUMENTED_TAGS,
    FOLLOW_THE_SPEAKER,
    VOICE_LANGUAGES,
    is_supported,
)


def test_the_documented_count():
    """Twenty entries plus auto-detect, exactly as xAI publishes them. A documented list that
    has quietly grown or shrunk is a list somebody edited from memory."""
    assert len(DOCUMENTED_TAGS) == 21
    assert DOCUMENTED_TAGS <= {tag for tag, _ in VOICE_LANGUAGES}


def test_persian_is_offered_although_it_is_not_documented():
    """Added on the strength of the model having been tried in it. The docs say it converses
    in languages beyond the list "with varying degrees of accuracy"; Persian is one of them."""
    assert is_supported("fa")
    assert "fa" not in DOCUMENTED_TAGS


def test_turkish_was_documented_all_along():
    """Named beside Persian in the same request, and already on the list. Worth pinning so a
    later reader does not go looking for how it was added."""
    assert is_supported("tr")
    assert "tr" in DOCUMENTED_TAGS


def test_the_two_provenances_stay_distinguishable():
    """Vendor promise and our own testing are not the same kind of claim. Once they are one
    undifferentiated list, nobody can tell which entries to re-check when the docs change."""
    offered = {tag for tag, _ in VOICE_LANGUAGES}
    assert offered - DOCUMENTED_TAGS == {"fa"}


def test_auto_is_first_and_is_the_default():
    """Following the speaker is what every Salon has done until now, so it is what an
    untouched control has to mean."""
    assert VOICE_LANGUAGES[0][0] == FOLLOW_THE_SPEAKER == "auto"


def test_the_regional_variants_are_kept_apart():
    """Seven of the twenty are regional. A caller in Cairo and one in Riyadh are both "Arabic"
    to a language column and are not the same voice; pt-BR read to somebody in Lisbon is
    noticeably wrong."""
    tags = [tag for tag, _ in VOICE_LANGUAGES]
    for regional in ("ar-EG", "ar-SA", "ar-AE", "pt-BR", "pt-PT", "es-MX", "es-ES"):
        assert regional in tags


def test_a_base_tag_is_not_accepted_for_a_language_that_has_variants():
    """`es` is not `es-MX`. Accepting the base tag would leave the model to pick an accent on
    the caller's behalf — the decision the host was making by setting this at all."""
    for base in ("es", "pt", "ar"):
        assert not is_supported(base)


def test_a_language_with_no_variant_is_named_plainly():
    for plain in ("en", "fr", "de", "ja", "ko", "ru", "tr", "vi", "hi", "bn", "id", "it", "zh"):
        assert is_supported(plain)


def test_nothing_outside_the_list_is_supported():
    for absent in ("", None, "xx", "fr-CA", "en-GB", "zh-TW"):
        assert not is_supported(absent)


def test_every_entry_carries_an_endonym():
    """Named in its own language, as the caption picker already does. A speaker of Bengali
    looking for their language will not find "Bengali"."""
    for tag, label in VOICE_LANGUAGES:
        assert label and label.strip()
        if tag not in ("auto", "en"):
            assert label != tag
