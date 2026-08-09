"""Taking the "euh" out and leaving the silences that mean something in.

Cleaning happens once, at ingestion, and every listener benefits — the alternative is doing
it N times on the way out, which costs N times as much to arrive at the same journal.

The line it must not cross is the one between cleaning and condensing (FR53). Hesitation
goes; not one word that carries meaning does. A cleaner that "tightens" a sentence is
paraphrasing somebody without telling them.

A pause is the interesting case, because silence is not always nothing. Under
`SIGNIFICANT_PAUSE_MS` it is breathing and it goes with the rest. Over it, it was doing
work — so it survives as `[pause=N]`, a metadata marker that is never pronounced, never
injectable by saying it out loud, and not counted as content.
"""
import pytest

from src.journal import (
    MAX_PAUSE_MS,
    SIGNIFICANT_PAUSE_MS,
    clean,
    pause_marker,
    pause_seconds,
    spoken_length,
    without_markers,
)


# ── The thresholds ────────────────────────────────────────────────────────────


def test_the_thresholds_are_the_ones_the_story_names():
    assert SIGNIFICANT_PAUSE_MS == 2000
    assert MAX_PAUSE_MS == 5000


def test_they_move_independently():
    """Two settings, not one with a multiplier. What counts as meaningful and how long a
    silence may be reproduced are different questions."""
    assert SIGNIFICANT_PAUSE_MS < MAX_PAUSE_MS


# ── Pauses ────────────────────────────────────────────────────────────────────


def test_a_short_pause_leaves_nothing_behind():
    """Breathing. It goes with the rest of the disfluency."""
    assert pause_marker(500) == ""
    assert pause_marker(SIGNIFICANT_PAUSE_MS) == ""


def test_a_pause_that_was_doing_work_survives_as_metadata():
    assert pause_marker(4000) == "[pause=4000]"


def test_a_very_long_silence_is_capped():
    """Thirty seconds of silence becomes five. Reproducing it faithfully would mean
    reproducing the moment somebody assumed the call had dropped."""
    assert pause_marker(30_000) == f"[pause={MAX_PAUSE_MS}]"


def test_a_marker_is_worth_its_milliseconds_when_the_lag_is_computed():
    """The silence occupies real time in the restitution, so it counts against the reader
    who has not reached it yet."""
    assert pause_seconds("Alors [pause=4000] voilà") == 4.0
    assert pause_seconds("rien du tout") == 0.0


def test_several_markers_add_up():
    assert pause_seconds("[pause=3000] et [pause=2500]") == 5.5


# ── Markers are not content ───────────────────────────────────────────────────


def test_a_marker_does_not_count_towards_the_size_of_a_message():
    """It is not speech. Counting it would cut interventions shorter than the 500
    characters of Story 6.5 promises, for a reason nobody could hear."""
    assert spoken_length("Bonjour[pause=4000] Marie") == spoken_length("Bonjour Marie")


def test_stripping_markers_leaves_the_words():
    assert without_markers("Alors [pause=4000] voilà") == "Alors voilà"


def test_stripping_markers_does_not_glue_words_together():
    assert without_markers("Alors[pause=3000]voilà") == "Alors voilà"


def test_a_message_of_nothing_but_silence_has_no_content():
    assert spoken_length("[pause=5000]") == 0


# ── Nobody can inject a marker by saying one ──────────────────────────────────


def test_saying_the_marker_out_loud_does_not_produce_one():
    """A participant reading "[pause=4000]" aloud is a participant saying words. Letting
    that become metadata would let anybody put silence into anybody else's ears."""
    cleaned = clean("je dis crochet pause égale 4000 crochet")

    assert pause_seconds(cleaned) == 0.0


def test_a_transcript_containing_the_literal_marker_is_neutralised():
    cleaned = clean("il a écrit [pause=4000] dans le document")

    assert pause_seconds(cleaned) == 0.0
    assert "4000" in cleaned


def test_a_marker_shaped_string_of_any_key_is_neutralised():
    """Story 6.11 says later markers share the form `[key=value]`. Neutralising only
    `pause` would leave the next one injectable from the day it ships."""
    cleaned = clean("il a dit [emphase=forte] et puis voilà")

    assert "[emphase=forte]" not in cleaned


# ── Cleaning ──────────────────────────────────────────────────────────────────


def test_a_hesitation_is_removed():
    assert clean("Alors euh je pense que oui") == "Alors je pense que oui"


@pytest.mark.parametrize(
    "hesitation",
    ["euh", "heu", "hum", "um", "uh", "erm", "ähm", "eh"],
)
def test_hesitations_are_removed_in_several_languages(hesitation):
    """A Salon is multilingual by construction, so a French-only filler list would clean
    one participant's speech and leave everybody else's untouched."""
    assert clean(f"Bonjour {hesitation} Marie") == "Bonjour Marie"


def test_a_repeated_word_is_said_once():
    """An involuntary repetition. Somebody who says "je je pense" said "je pense"."""
    assert clean("je je pense que oui") == "je pense que oui"


def test_a_repetition_across_a_hesitation_is_still_a_repetition():
    assert clean("je euh je pense") == "je pense"


def test_a_repeated_longer_word_is_left_alone():
    """People stammer on function words. Repeating a longer one is usually deliberate —
    "très très bien" means something "très bien" does not — and the asymmetry decides it:
    missing a stammer costs a repeated syllable, deleting an intended word costs a meaning
    in a language the listener cannot check."""
    assert clean("c'est très très bien") == "c'est très très bien"


def test_not_one_word_that_carries_meaning_is_removed():
    """The line between cleaning and condensing (FR53). A cleaner that shortens a sentence
    is paraphrasing somebody without telling them."""
    said = "Je pense que nous devrions reporter la réunion de mardi à jeudi prochain."

    assert clean(said) == said


def test_nothing_is_reformulated():
    said = "Il faut que tu saches que je ne suis pas d'accord du tout avec cette approche."

    assert clean(said) == said


def test_a_turn_that_was_nothing_but_hesitation_comes_back_empty():
    """There is nothing to render to anybody, and the journal refuses an empty message —
    so a turn of pure hesitation occupies no position at all."""
    assert clean("euh... hum, euh") == ""


def test_cleaning_nothing_is_nothing():
    assert clean("") == ""
    assert clean(None) == ""


def test_whitespace_is_tidied_rather_than_left_where_a_word_was():
    assert clean("Bonjour   euh   Marie") == "Bonjour Marie"


def test_a_capitalised_hesitation_is_still_a_hesitation():
    assert clean("Euh, je pense") == "je pense"


def test_a_word_that_merely_contains_a_filler_is_not_touched():
    """"heureux" starts with "heu". Removing it would delete a word for looking like a
    noise, which is exactly the failure this whole story is trying to avoid."""
    assert clean("je suis heureux") == "je suis heureux"
    assert clean("un humble avis") == "un humble avis"


def test_a_pause_marker_survives_the_cleaning_it_was_added_by():
    """The adapter inserts the marker, then cleans. The cleaning must not take out what the
    adapter just decided was worth keeping."""
    assert clean("Alors [pause=4000] voilà", keep_markers=True) == "Alors [pause=4000] voilà"


# ── Cleaned once, at ingestion ────────────────────────────────────────────────


async def test_a_message_reaches_the_journal_already_cleaned():
    """The acceptance criterion that matters most: the journal holds useful content only,
    so every listener benefits from one cleaning rather than each paying for their own."""
    from src.interprete import InterpreteFake, Participant
    from src.journal import InMemoryJournalStore, SalonLog
    from src.salon import InMemoryRoomProvisioner, Salon

    async def translate(text, *, source, target):
        return text

    marie = Participant(id="marie", language="fr", name="Marie")
    log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate)
    salon = Salon(log=log, rooms=InMemoryRoomProvisioner())
    await salon.join(marie, InterpreteFake(participant=marie))

    (entry,) = await salon.ingest(marie.id, "Alors euh je je pense que oui", language="fr")

    assert entry.text == "Alors je pense que oui"


async def test_a_turn_of_pure_hesitation_never_becomes_a_message():
    from src.interprete import InterpreteFake, Participant
    from src.journal import InMemoryJournalStore, SalonLog
    from src.salon import InMemoryRoomProvisioner, Salon

    async def translate(text, *, source, target):
        return text

    marie = Participant(id="marie", language="fr", name="Marie")
    log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate)
    salon = Salon(log=log, rooms=InMemoryRoomProvisioner())
    await salon.join(marie, InterpreteFake(participant=marie))

    assert await salon.ingest(marie.id, "euh... hum", language="fr") == ()
    assert log.entries == ()


async def test_a_pause_survives_into_the_journal_and_counts_against_a_reader():
    """The marker is kept and the silence it stands for is charged in full — Story 7.2
    weighs exactly this against its condensation threshold."""
    from src.interprete import InterpreteFake, Participant
    from src.journal import InMemoryJournalStore, SalonLog
    from src.salon import InMemoryRoomProvisioner, Salon

    async def translate(text, *, source, target):
        return text

    marie = Participant(id="marie", language="fr", name="Marie")
    log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate)
    salon = Salon(log=log, rooms=InMemoryRoomProvisioner())
    await salon.join(marie, InterpreteFake(participant=marie))

    (entry,) = await salon.ingest(marie.id, "Alors [pause=4000] voilà", language="fr")

    assert "[pause=4000]" in entry.text
    assert entry.duration_seconds >= 4.0


async def test_cleaning_shortens_what_every_room_has_left_to_say():
    """Cleaning at ingestion reduces the lag of every room at once. That is the whole
    argument for doing it here rather than once per listener: one pass, N beneficiaries."""
    from src.interprete import InterpreteFake, Participant
    from src.journal import InMemoryJournalStore, SalonLog, content_seconds
    from src.salon import InMemoryRoomProvisioner, Salon

    async def translate(text, *, source, target):
        return text

    said = "Alors euh je je pense que oui"
    marie = Participant(id="marie", language="fr", name="Marie")
    hans = Participant(id="hans", language="de", name="Hans")
    log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate)
    salon = Salon(log=log, rooms=InMemoryRoomProvisioner())
    await salon.join(marie, InterpreteFake(participant=marie))
    await salon.join(hans, InterpreteFake(participant=hans))

    await salon.ingest(marie.id, said, language="fr")

    assert salon.log.lag_seconds("hans") < content_seconds(said)


# ── A marker is never pronounced ──────────────────────────────────────────────


def test_a_voice_is_never_given_the_marker_to_say():
    """The one outcome nothing may produce: an interpreter reading "[pause=4000]" at
    somebody. The marker says *how* to say the rest, not what to say."""
    from src.interprete import Utterance

    utterance = Utterance(text="Alors [pause=4000] voilà", language="fr", source_language="fr")

    assert utterance.spoken_text == "Alors voilà"
    assert "[pause" not in utterance.spoken_text


def test_the_silence_is_an_indication_of_intent():
    """Applied idiomatically — the same beat is shorter in one language than another — so
    what the port carries is the duration, not an instruction to the hundredth."""
    from src.interprete import Utterance

    utterance = Utterance(text="Alors [pause=4000] voilà", language="de", source_language="fr")

    assert utterance.pause_seconds == 4.0


def test_something_with_no_silence_in_it_asks_for_none():
    from src.interprete import Utterance

    assert Utterance(text="Bonjour", language="fr", source_language="fr").pause_seconds == 0.0
