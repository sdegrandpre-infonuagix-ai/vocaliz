"""Reading the conversation while you hear it.

Captions are not a lesser copy of the voice. They reach further: text renders into languages
no realtime model can pronounce, so somebody can follow a Salon in a language they could
never be spoken to in. That asymmetry is the point of the feature, not an implementation
detail — the spoken set is the intersection of the adapters, and the caption set is wider on
purpose.

They travel the data channel of the reader's own room. Never the audio path: a caption is
text, and putting text where the audio goes would be a second thing in a room that holds
exactly one human and one interpreter.
"""
import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import (
    AS_SPOKEN,
    DEFAULT_CAPTION_SCALE,
    InMemoryRoomProvisioner,
    Salon,
    caption_languages,
    captions_offered_in,
)

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
# Welsh: the Base chain renders it as text, no realtime voice speaks it.
RHYS = Participant(id="rhys", language="cy", name="Rhys")


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def rooms():
    return InMemoryRoomProvisioner()


@pytest.fixture
def salon(rooms):
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(log=log, rooms=rooms)


async def _join(salon, participant, **kwargs):
    return await salon.join(participant, InterpreteFake(participant=participant), **kwargs)


def _captions(rooms, room):
    return [payload.decode() for payload in rooms.published(room)]


# ── Off until chosen, and remembered once it is ───────────────────────────────


async def test_captions_are_not_on_until_somebody_chooses(salon, rooms):
    """`None` means never chosen — which is not the same as choosing to read the original."""
    await _join(salon, MARIE)

    assert salon.caption_language(MARIE.id) is None
    assert salon.reads_captions(MARIE.id) is False


async def test_choosing_a_language_turns_them_on(salon):
    await _join(salon, MARIE)

    await salon.set_captions(MARIE.id, language="fr")

    assert salon.caption_language(MARIE.id) == "fr"
    assert salon.reads_captions(MARIE.id) is True


async def test_as_spoken_is_a_choice_in_its_own_right(salon):
    """`""` means "show me the original, translate nothing" — a decision somebody made,
    and distinct from never having decided."""
    await _join(salon, MARIE)

    await salon.set_captions(MARIE.id, language=AS_SPOKEN)

    assert salon.caption_language(MARIE.id) == AS_SPOKEN
    assert salon.reads_captions(MARIE.id) is True


async def test_turning_them_off_again_is_not_the_same_as_never_choosing(salon):
    await _join(salon, MARIE)
    await salon.set_captions(MARIE.id, language="fr")

    await salon.set_captions(MARIE.id, language=None)

    assert salon.caption_language(MARIE.id) is None
    assert salon.reads_captions(MARIE.id) is False


async def test_the_size_is_a_setting_of_its_own(salon):
    """It follows the account rather than the device: somebody who needs larger text needs
    it on their telephone as well as on their laptop."""
    await _join(salon, MARIE)

    await salon.set_captions(MARIE.id, language="fr", scale=1.5)

    assert salon.caption_scale(MARIE.id) == 1.5


async def test_the_size_has_a_sensible_default(salon):
    await _join(salon, MARIE)
    await salon.set_captions(MARIE.id, language="fr")

    assert salon.caption_scale(MARIE.id) == DEFAULT_CAPTION_SCALE


async def test_settings_for_somebody_who_is_not_here_change_nothing(salon):
    await salon.set_captions("nobody", language="fr")

    assert salon.reads_captions("nobody") is False


# ── What each reader gets ─────────────────────────────────────────────────────


async def test_a_reader_gets_each_turn_in_their_own_caption_language(salon, rooms):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.set_captions(HANS.id, language="de")

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _captions(rooms, await salon.room_of(HANS.id)) == ["Bonjour [de]"]


async def test_two_readers_choose_independently(salon, rooms):
    """One person reading in Welsh does not decide what anybody else reads."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, RHYS)
    await salon.set_captions(HANS.id, language="de")
    await salon.set_captions(RHYS.id, language="cy")

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _captions(rooms, await salon.room_of(HANS.id)) == ["Bonjour [de]"]
    assert _captions(rooms, await salon.room_of(RHYS.id)) == ["Bonjour [cy]"]


async def test_somebody_who_chose_nothing_is_sent_no_captions(salon, rooms):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _captions(rooms, await salon.room_of(HANS.id)) == []


async def test_a_turn_already_in_the_reading_language_is_shown_as_spoken(salon, rooms):
    """No translation and no translation row: there is nothing to do and nothing to keep."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.set_captions(HANS.id, language="fr")

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _captions(rooms, await salon.room_of(HANS.id)) == ["Bonjour"]


async def test_as_spoken_shows_the_original_whatever_it_was(salon, rooms):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.set_captions(HANS.id, language=AS_SPOKEN)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _captions(rooms, await salon.room_of(HANS.id)) == ["Bonjour"]


async def test_nobody_reads_their_own_words_back(salon, rooms):
    await _join(salon, MARIE)
    await salon.set_captions(MARIE.id, language="fr")

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _captions(rooms, await salon.room_of(MARIE.id)) == []


async def test_a_pause_marker_is_never_displayed(salon, rooms):
    """It is metadata about how to say something. There is nothing to read in a silence."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.set_captions(HANS.id, language=AS_SPOKEN)

    await salon.ingest(MARIE.id, "Alors [pause=4000] voilà", language="fr")
    await salon.deliver_all()

    assert _captions(rooms, await salon.room_of(HANS.id)) == ["Alors voilà"]


# ── One translation, shared ───────────────────────────────────────────────────


async def test_three_readers_in_one_language_cost_one_translation(salon):
    """The cache is keyed on (turn, language) and captions use the same one the voice does —
    a turn read by three people in German is translated once."""
    calls = []

    async def counted(text, *, source, target):
        calls.append(target)
        return f"{text} [{target}]"

    log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=counted)
    shared = Salon(log=log, rooms=InMemoryRoomProvisioner())
    luc = Participant(id="luc", language="de", name="Luc")
    anne = Participant(id="anne", language="de", name="Anne")
    for participant in (MARIE, HANS, luc, anne):
        await shared.join(participant, InterpreteFake(participant=participant))
    for reader in (HANS, luc, anne):
        await shared.set_captions(reader.id, language="de")

    await shared.ingest(MARIE.id, "Bonjour", language="fr")
    await shared.deliver_all()

    assert calls == ["de"]


async def test_every_caption_is_one_hop_from_the_original(salon):
    """Never a translation of a translation, which is exactly what a cache keyed on the
    original guarantees."""
    calls = []

    async def counted(text, *, source, target):
        calls.append((text, source, target))
        return f"{text} [{target}]"

    log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=counted)
    chained = Salon(log=log, rooms=InMemoryRoomProvisioner())
    for participant in (MARIE, HANS, RHYS):
        await chained.join(participant, InterpreteFake(participant=participant))
    await chained.set_captions(HANS.id, language="de")
    await chained.set_captions(RHYS.id, language="cy")

    await chained.ingest(MARIE.id, "Bonjour", language="fr")
    await chained.deliver_all()

    assert {text for text, _, _ in calls} == {"Bonjour"}
    assert {source for _, source, _ in calls} == {"fr"}


# ── Wider than the voice ──────────────────────────────────────────────────────


def test_more_languages_can_be_read_than_spoken():
    """The whole reason this feature is not just a transcript of the audio: text reaches
    languages a realtime voice does not."""
    spoken = captions_offered_in()

    assert caption_languages() > spoken
    assert caption_languages() >= spoken


def test_a_language_only_text_supports_is_offered_for_reading():
    assert "cy" in caption_languages()


def test_the_spoken_set_is_still_the_intersection_of_the_adapters():
    """Story 6.7 is unchanged by this. Being able to read Welsh is not being able to be
    spoken to in it."""
    assert "cy" not in captions_offered_in()


async def test_somebody_reading_a_language_nobody_speaks_still_reads_it(salon, rooms):
    """Only the voice falls back. The captions are exactly what they asked for."""
    await _join(salon, MARIE)
    await _join(salon, RHYS)
    await salon.set_captions(RHYS.id, language="cy")

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _captions(rooms, await salon.room_of(RHYS.id)) == ["Bonjour [cy]"]


# ── The data channel, never the audio path ────────────────────────────────────


async def test_captions_travel_the_readers_own_room(salon, rooms):
    """Their room and nobody else's — the same isolation that makes echo impossible."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, RHYS)
    await salon.set_captions(HANS.id, language="de")

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _captions(rooms, await salon.room_of(RHYS.id)) == []
    assert _captions(rooms, await salon.room_of(MARIE.id)) == []


async def test_a_caption_is_never_spoken(salon):
    """It is something to read. Sending it to the voice would say everything twice."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.set_captions(HANS.id, language="de")

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    spoken = [line.text for line in salon.interpreter_of(HANS.id).spoken]
    assert spoken.count("Bonjour [de]") == 0


async def test_a_reader_who_left_is_sent_nothing(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.set_captions(HANS.id, language="de")

    await salon.leave(HANS.id)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert salon.reads_captions(HANS.id) is False
