"""Introducing each participant, and the language they turned out to speak.

The topology takes away the two things that normally tell you who is talking: you never
hear anybody's real voice, and everything reaches you in your own language. Without an
introduction, a Salon is a series of sentences from nowhere.

So the trigger is the first thing somebody actually says, not their arrival. A language is
detected, never declared — introducing somebody before they have spoken would mean either
inventing a language for them or introducing them twice.

And it is once per listener per Salon. An introduction repeated is an introduction that
stops being heard.
"""
import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
RHYS = Participant(id="rhys", language="cy", name="Rhys")
# No name: an invitation the host never put a name to. FR57's telephone participant is the
# common case, and their number must never become their label.
UNNAMED = Participant(id="+15145550123", language="en")


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def salon():
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(log=log, rooms=InMemoryRoomProvisioner())


async def _join(salon, participant, **kwargs):
    return await salon.join(participant, InterpreteFake(participant=participant), **kwargs)


def _lines(salon, participant_id):
    return salon.interpreter_of(participant_id).spoken


def _annonces(salon, participant_id):
    return [line.text for line in _lines(salon, participant_id) if line.kind == "annonce"]


# ── The first time somebody speaks ────────────────────────────────────────────


async def test_speaking_for_the_first_time_introduces_you_to_the_others(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert len(_annonces(salon, HANS.id)) == 1
    assert "Marie" in _annonces(salon, HANS.id)[0]


async def test_the_introduction_names_the_language_they_spoke(salon):
    """Detected, never declared. What is announced is what they were actually heard in."""
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert "Französisch" in _annonces(salon, HANS.id)[0]


async def test_the_introduction_is_in_the_listeners_own_language(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, RHYS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert [line.language for line in _lines(salon, HANS.id) if line.kind == "annonce"] == ["de"]
    assert [line.language for line in _lines(salon, RHYS.id) if line.kind == "annonce"] == ["cy"]


async def test_the_introduction_comes_immediately_before_their_first_message(salon):
    """You know who is speaking before you hear what they say. The other order is a
    sentence from nowhere followed by an explanation of who said it."""
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert [line.kind for line in _lines(salon, HANS.id)] == ["annonce", "tour"]


async def test_nobody_is_introduced_to_themselves(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _annonces(salon, MARIE.id) == []


async def test_somebody_is_introduced_once_and_not_again(salon):
    """An introduction repeated is an introduction that stops being heard."""
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()
    await salon.ingest(MARIE.id, "Ça va ?", language="fr")
    await salon.deliver_all()

    assert len(_annonces(salon, HANS.id)) == 1
    assert [line.kind for line in _lines(salon, HANS.id)] == ["annonce", "tour", "tour"]


async def test_each_speaker_gets_their_own_introduction(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, RHYS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.ingest(HANS.id, "Guten Tag", language="de")
    await salon.deliver_all()

    assert len(_annonces(salon, RHYS.id)) == 2


async def test_somebody_who_has_not_spoken_is_never_introduced(salon):
    """No language is invented for them. They are introduced when they say something, and
    a Salon where somebody stays silent throughout never mentions them at all."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, RHYS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert len(_annonces(salon, HANS.id)) == 1
    assert "Rhys" not in " ".join(_annonces(salon, HANS.id))


async def test_a_participant_who_switches_language_is_still_introduced_once(salon):
    """The introduction records what they were first heard in, and is not revised. Saying
    "Marie now speaks English" mid-conversation is noise, not information."""
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()
    await salon.ingest(MARIE.id, "Actually, in English", language="en")
    await salon.deliver_all()

    assert len(_annonces(salon, HANS.id)) == 1


# ── Arriving after the conversation has started ───────────────────────────────


async def test_an_arrival_is_told_who_is_already_here(salon):
    """Their room is ready and the conversation is already running. Without this they meet
    three strangers one sentence at a time."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.ingest(HANS.id, "Guten Tag", language="de")

    await _join(salon, RHYS)

    (announcement,) = _annonces(salon, RHYS.id)
    assert "Marie" in announcement and "Hans" in announcement


async def test_the_arrival_announcement_is_in_the_arrivals_language(salon):
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    await _join(salon, HANS)

    assert [line.language for line in _lines(salon, HANS.id)] == ["de"]


async def test_an_arrival_is_not_told_about_people_who_have_not_spoken(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    await _join(salon, RHYS)

    assert "Hans" not in _annonces(salon, RHYS.id)[0]


async def test_an_arrival_into_a_silent_salon_is_told_nothing(salon):
    """Nobody has spoken, so there is nobody to introduce and no language to name."""
    await _join(salon, MARIE)

    await _join(salon, HANS)

    assert _annonces(salon, HANS.id) == []


async def test_an_arrival_is_not_introduced_to_them_all_over_again(salon):
    """They have just been told. Hearing it again with the first sentence would be the same
    introduction twice within seconds."""
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    await _join(salon, HANS, from_start=True)
    await salon.deliver_all()

    assert len(_annonces(salon, HANS.id)) == 1


async def test_the_arrival_is_themselves_introduced_when_they_speak(salon):
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await _join(salon, HANS)

    await salon.ingest(HANS.id, "Guten Tag", language="de")
    await salon.deliver_all()

    assert "Hans" in " ".join(_annonces(salon, MARIE.id))


# ── When everybody speaks the same language ───────────────────────────────────


async def test_a_salon_in_one_language_says_so_rather_than_listing_everybody(salon):
    """Naming each person's language when it is everybody's is three sentences that carry
    one bit between them."""
    luc = Participant(id="luc", language="fr", name="Luc")
    anne = Participant(id="anne", language="fr", name="Anne")
    await _join(salon, MARIE)
    await _join(salon, luc)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.ingest(luc.id, "Salut", language="fr")

    await _join(salon, anne)

    (announcement,) = _annonces(salon, anne.id)
    assert "français" in announcement.lower()
    assert "Marie" not in announcement and "Luc" not in announcement


# ── Names ─────────────────────────────────────────────────────────────────────


async def test_somebody_with_no_name_gets_a_neutral_designation(salon):
    await _join(salon, MARIE)
    await _join(salon, UNNAMED)

    await salon.ingest(UNNAMED.id, "Hello", language="en")
    await salon.deliver_all()

    assert _annonces(salon, MARIE.id) != []


async def test_a_telephone_number_is_never_read_out_as_a_name(salon):
    """FR57. Their number is how they reached the Salon, not who they are, and the others
    have no business being told it."""
    await _join(salon, MARIE)
    await _join(salon, UNNAMED)

    await salon.ingest(UNNAMED.id, "Hello", language="en")
    await salon.deliver_all()

    assert "+15145550123" not in " ".join(_annonces(salon, MARIE.id))
    assert "5145550123" not in " ".join(_annonces(salon, MARIE.id))


async def test_a_telephone_participant_is_introduced_like_anybody_else(salon):
    """FR57 again, from the other side: no special case, and they get the arrival
    announcement too."""
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    await _join(salon, UNNAMED)

    assert "Marie" in _annonces(salon, UNNAMED.id)[0]


async def test_somebody_who_left_is_still_named_in_what_they_said(salon):
    """Their words stay in the journal, so a late arrival given the history hears them —
    and hears who said them."""
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.leave(MARIE.id)

    await _join(salon, HANS, from_start=True)
    await salon.deliver_all()

    assert "Marie" in " ".join(_annonces(salon, HANS.id))


# ── The notices themselves ────────────────────────────────────────────────────


def test_an_announcement_about_nobody_is_no_announcement():
    """The conductor never calls it with an empty list, but it is the answer that keeps the
    function honest on its own: there is nothing to say, so it says nothing rather than
    producing a sentence with a hole in it."""
    from src.salon.notices import already_here

    assert already_here([], told_in="fr") is None


def test_an_unknown_language_is_named_by_its_code():
    """Wrong but legible, and it is the code the adapters themselves use — so a language
    nobody has translated the name of is at least traceable to where it came from."""
    from src.salon.notices import introduces

    assert "qx" in introduces("Marie", "qx", told_in="fr")


def test_a_listener_in_an_untranslated_language_still_hears_something():
    """English rather than silence. A sentence in the wrong language still says somebody is
    here; nothing said says nothing at all."""
    from src.salon.notices import introduces

    assert introduces("Marie", "fr", told_in="qx") == "Marie speaks French."
