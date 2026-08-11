"""Tests for transcription and live translation — storing speech, rendering it elsewhere."""
from unittest.mock import patch

import pytest

from src.models.salon import Salon
from src.models.utterance import Utterance, UtteranceTranslation
from src.models.user import User
from src.services import translation_service, utterance_service
from src.services.jwt_service import issue_token


@pytest.fixture
def host(db):
    u = User(email="host@example.com")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def salon(db, host):
    user, _ = host
    s = Salon(
        host_user_id=user.id,
        livekit_room_name="salon-transcript",
        source_type="url",
        source_content="content",
        status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _post(client, token, salon, **overrides):
    body = {
        "speakerIdentity": "guest-3f2a1b4c-0000-0000-0000-000000000000",
        "speakerRole": "guest",
        "text": "Necesito el informe.",
        "language": "es",
    }
    body.update(overrides)
    return client.post(
        f"/salons/{salon.id}/utterances", json=body, headers=_auth(token)
    )


# ─── Language normalisation ───────────────────────────────────────────────────

def test_region_is_dropped_for_codes_translate_does_not_know():
    """Amazon Translate rejects en-US where it accepts en."""
    assert translation_service.normalise("en-US") == "en"
    assert translation_service.normalise("en_CA") == "en"


def test_regional_variants_translate_knows_are_kept():
    """Quebec French is not France French, and the translator can tell them apart."""
    assert translation_service.normalise("fr-CA") == "fr-ca"
    assert translation_service.normalise("pt-BR") == "pt-br"


def test_blank_language_is_none():
    for value in (None, "", "   "):
        assert translation_service.normalise(value) is None


def test_same_language_compares_primary_subtags_only():
    """Someone reading in 'fr' needs no translation of a turn spoken in 'fr-CA'."""
    assert translation_service.same_language("fr-CA", "fr")
    assert not translation_service.same_language("fr", "en")
    # A missing language is not a match — it must not silently skip translation.
    assert not translation_service.same_language(None, "fr")


# ─── Storing speech ───────────────────────────────────────────────────────────

def test_records_a_turn_with_its_sequence(client, host, salon):
    _, token = host
    body = _post(client, token, salon).json()
    assert body["sequence"] == 1
    assert body["text"] == "Necesito el informe."
    assert body["language"] == "es"


def test_sequence_increments_per_salon(client, host, salon):
    _, token = host
    for expected in (1, 2, 3):
        assert _post(client, token, salon).json()["sequence"] == expected


def test_blank_text_is_rejected(client, host, salon):
    """A silent turn is not a caption, and an empty row would break the ordering."""
    _, token = host
    assert _post(client, token, salon, text="   ").status_code == 422


def test_unknown_speaker_role_is_rejected(client, host, salon):
    _, token = host
    assert _post(client, token, salon, speakerRole="moderator").status_code == 422


def test_another_hosts_salon_is_not_writable(client, db, salon):
    """Ownership of the salon is the authorisation, so a stranger's token must fail."""
    other = User(email="stranger@example.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    assert _post(client, issue_token(str(other.id)), salon).status_code == 404


# ─── Who a caption is attributed to ───────────────────────────────────────────

def test_a_guest_is_labelled_not_named(client, host, salon):
    """The host typed that address to invite them; nobody else may read it."""
    _, token = host
    assert _post(client, token, salon).json()["speaker"] == "Guest 3F2A"


def test_the_agent_is_labelled_vocaliz(client, host, salon):
    _, token = host
    body = _post(
        client, token, salon, speakerIdentity="agent", speakerRole="agent", text="Welcome."
    ).json()
    assert body["speaker"] == "Vocaliz"


def test_a_given_name_wins_over_the_anonymised_guess(client, host, salon):
    """LiveKit's own display name for a guest who gave one — passed through by the agent,
    which already holds it from the room, not looked up here."""
    _, token = host
    body = _post(client, token, salon, speakerName="Marie").json()
    assert body["speaker"] == "Marie"


def test_a_shared_line_is_labelled_salon_not_vocaliz(client, host, salon):
    """A typed message read aloud on the sender's behalf is the agent's voice but not the
    agent's own words — "Salon" says so, where the bare role would say "Vocaliz"."""
    _, token = host
    body = _post(
        client, token, salon,
        speakerIdentity="agent", speakerRole="agent", speakerName="Salon", text="Bonjour à tous.",
    ).json()
    assert body["speaker"] == "Salon"


def test_a_blank_name_falls_back_to_the_anonymised_guess(client, host, salon):
    """An empty string is not a name — the agent sends one for every guest whether or not
    they gave one, so this is what keeps an unnamed guest anonymised rather than blank."""
    _, token = host
    body = _post(client, token, salon, speakerName="   ").json()
    assert body["speaker"] == "Guest 3F2A"


def test_a_given_name_survives_into_the_replayed_transcript(client, host, salon):
    """The name a late joiner sees must be the one a live listener saw — not whatever the
    anonymised guess resolves to by the time they ask."""
    _, token = host
    _post(client, token, salon, speakerName="Marie")

    body = client.get(f"/salons/{salon.id}/utterances", headers=_auth(token)).json()
    assert body["utterances"][0]["speaker"] == "Marie"


# ─── Translating ──────────────────────────────────────────────────────────────

def test_translation_is_returned_for_each_requested_language(client, host, salon):
    _, token = host
    with patch.object(translation_service, "translate", return_value="J'ai besoin du rapport."):
        body = _post(client, token, salon, targetLanguages=["fr"]).json()
    assert body["translations"] == {"fr": "J'ai besoin du rapport."}
    # The spoken text is never replaced by its translation.
    assert body["text"] == "Necesito el informe."


def test_no_call_is_made_when_the_turn_is_already_in_that_language(client, host, salon):
    """Paying to turn Spanish into Spanish also risks it being quietly rephrased."""
    _, token = host
    with patch.object(translation_service, "translate") as translate:
        body = _post(client, token, salon, targetLanguages=["es"]).json()
    translate.assert_not_called()
    assert body["translations"] == {"es": "Necesito el informe."}


def test_a_failed_translation_is_absent_rather_than_echoed(client, host, salon):
    """An absent key means 'not translated'. Echoing the original would hide the failure."""
    _, token = host
    with patch.object(translation_service, "translate", return_value=None):
        body = _post(client, token, salon, targetLanguages=["fr"]).json()
    assert body["translations"] == {}
    assert body["text"] == "Necesito el informe."


def test_translations_are_cached_per_language(client, db, host, salon):
    """A second viewer reading in the same language must not cost a second call."""
    _, token = host
    with patch.object(
        translation_service, "translate", return_value="J'ai besoin du rapport."
    ) as translate:
        _post(client, token, salon, targetLanguages=["fr"])
        client.get(
            f"/salons/{salon.id}/utterances?lang=fr", headers=_auth(token)
        )
    assert translate.call_count == 1
    assert db.query(UtteranceTranslation).count() == 1


# ─── Reading back ─────────────────────────────────────────────────────────────

def test_transcript_returns_turns_in_order(client, host, salon):
    _, token = host
    _post(client, token, salon, text="Primero.")
    _post(client, token, salon, text="Segundo.")
    body = client.get(f"/salons/{salon.id}/utterances", headers=_auth(token)).json()
    assert [u["text"] for u in body["utterances"]] == ["Primero.", "Segundo."]


def test_after_skips_what_the_client_already_has(client, host, salon):
    """A sequence number, not a timestamp: a clock skew must not lose a turn."""
    _, token = host
    _post(client, token, salon, text="Primero.")
    _post(client, token, salon, text="Segundo.")
    body = client.get(
        f"/salons/{salon.id}/utterances?after=1", headers=_auth(token)
    ).json()
    assert [u["sequence"] for u in body["utterances"]] == [2]


def test_transcript_carries_the_spoken_words_beside_the_translation(client, host, salon):
    """A translation with no original is a claim the viewer cannot check."""
    _, token = host
    _post(client, token, salon)
    with patch.object(translation_service, "translate", return_value="J'ai besoin du rapport."):
        body = client.get(
            f"/salons/{salon.id}/utterances?lang=fr", headers=_auth(token)
        ).json()
    turn = body["utterances"][0]
    assert turn["text"] == "J'ai besoin du rapport."
    assert turn["originalText"] == "Necesito el informe."


def test_transcript_echoes_the_language_it_answered_in(client, host, salon):
    """A request in flight can answer after a newer one; the client must be able to tell."""
    _, token = host
    body = client.get(
        f"/salons/{salon.id}/utterances?lang=de", headers=_auth(token)
    ).json()
    assert body["language"] == "de"


# ─── Failure must never interrupt a conversation ──────────────────────────────

def test_recording_returns_none_on_blank_text(db, salon):
    assert (
        utterance_service.record(
            db,
            salon_id=salon.id,
            speaker_identity="agent",
            speaker_role="agent",
            text="   ",
        )
        is None
    )


def test_a_translator_outage_still_yields_a_caption(db, salon):
    """Best-effort: an untranslated caption is a degraded conversation, not a broken one."""
    utterance = utterance_service.record(
        db,
        salon_id=salon.id,
        speaker_identity="agent",
        speaker_role="agent",
        text="Welcome.",
        language="en",
    )
    with patch.object(translation_service, "translate", return_value=None):
        assert translation_service.translated_text(db, utterance, "fr") == "Welcome."
    assert db.query(UtteranceTranslation).count() == 0


def test_only_finals_reach_the_table(client, host, salon):
    """The endpoint stores what it is given; interim revisions never get posted.

    Guards the contract the agent relies on: one row per turn, not one per revision of a
    sentence the model was still hearing.
    """
    _, token = host
    _post(client, token, salon, text="Necesito el informe.")
    assert db_count(salon) == 1


def db_count(salon):
    from tests.conftest import TestingSession

    with TestingSession() as s:
        return s.query(Utterance).filter(Utterance.salon_id == salon.id).count()
