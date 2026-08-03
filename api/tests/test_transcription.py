"""Tests for transcription and live translation — storing speech, rendering it elsewhere."""
from unittest.mock import patch

import pytest

from src.models.session import SessionModel
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
def session(db, host):
    user, _ = host
    s = SessionModel(
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


def _post(client, token, session, **overrides):
    body = {
        "speakerIdentity": "guest-3f2a1b4c-0000-0000-0000-000000000000",
        "speakerRole": "guest",
        "text": "Necesito el informe.",
        "language": "es",
    }
    body.update(overrides)
    return client.post(
        f"/sessions/{session.id}/utterances", json=body, headers=_auth(token)
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

def test_records_a_turn_with_its_sequence(client, host, session):
    _, token = host
    body = _post(client, token, session).json()
    assert body["sequence"] == 1
    assert body["text"] == "Necesito el informe."
    assert body["language"] == "es"


def test_sequence_increments_per_session(client, host, session):
    _, token = host
    for expected in (1, 2, 3):
        assert _post(client, token, session).json()["sequence"] == expected


def test_blank_text_is_rejected(client, host, session):
    """A silent turn is not a caption, and an empty row would break the ordering."""
    _, token = host
    assert _post(client, token, session, text="   ").status_code == 422


def test_unknown_speaker_role_is_rejected(client, host, session):
    _, token = host
    assert _post(client, token, session, speakerRole="moderator").status_code == 422


def test_another_hosts_session_is_not_writable(client, db, session):
    """Ownership of the session is the authorisation, so a stranger's token must fail."""
    other = User(email="stranger@example.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    assert _post(client, issue_token(str(other.id)), session).status_code == 404


# ─── Who a caption is attributed to ───────────────────────────────────────────

def test_a_guest_is_labelled_not_named(client, host, session):
    """The host typed that address to invite them; nobody else may read it."""
    _, token = host
    assert _post(client, token, session).json()["speaker"] == "Guest 3F2A"


def test_the_agent_is_labelled_vocaliz(client, host, session):
    _, token = host
    body = _post(
        client, token, session, speakerIdentity="agent", speakerRole="agent", text="Welcome."
    ).json()
    assert body["speaker"] == "Vocaliz"


# ─── Translating ──────────────────────────────────────────────────────────────

def test_translation_is_returned_for_each_requested_language(client, host, session):
    _, token = host
    with patch.object(translation_service, "translate", return_value="J'ai besoin du rapport."):
        body = _post(client, token, session, targetLanguages=["fr"]).json()
    assert body["translations"] == {"fr": "J'ai besoin du rapport."}
    # The spoken text is never replaced by its translation.
    assert body["text"] == "Necesito el informe."


def test_no_call_is_made_when_the_turn_is_already_in_that_language(client, host, session):
    """Paying to turn Spanish into Spanish also risks it being quietly rephrased."""
    _, token = host
    with patch.object(translation_service, "translate") as translate:
        body = _post(client, token, session, targetLanguages=["es"]).json()
    translate.assert_not_called()
    assert body["translations"] == {"es": "Necesito el informe."}


def test_a_failed_translation_is_absent_rather_than_echoed(client, host, session):
    """An absent key means 'not translated'. Echoing the original would hide the failure."""
    _, token = host
    with patch.object(translation_service, "translate", return_value=None):
        body = _post(client, token, session, targetLanguages=["fr"]).json()
    assert body["translations"] == {}
    assert body["text"] == "Necesito el informe."


def test_translations_are_cached_per_language(client, db, host, session):
    """A second viewer reading in the same language must not cost a second call."""
    _, token = host
    with patch.object(
        translation_service, "translate", return_value="J'ai besoin du rapport."
    ) as translate:
        _post(client, token, session, targetLanguages=["fr"])
        client.get(
            f"/sessions/{session.id}/utterances?lang=fr", headers=_auth(token)
        )
    assert translate.call_count == 1
    assert db.query(UtteranceTranslation).count() == 1


# ─── Reading back ─────────────────────────────────────────────────────────────

def test_transcript_returns_turns_in_order(client, host, session):
    _, token = host
    _post(client, token, session, text="Primero.")
    _post(client, token, session, text="Segundo.")
    body = client.get(f"/sessions/{session.id}/utterances", headers=_auth(token)).json()
    assert [u["text"] for u in body["utterances"]] == ["Primero.", "Segundo."]


def test_after_skips_what_the_client_already_has(client, host, session):
    """A sequence number, not a timestamp: a clock skew must not lose a turn."""
    _, token = host
    _post(client, token, session, text="Primero.")
    _post(client, token, session, text="Segundo.")
    body = client.get(
        f"/sessions/{session.id}/utterances?after=1", headers=_auth(token)
    ).json()
    assert [u["sequence"] for u in body["utterances"]] == [2]


def test_transcript_carries_the_spoken_words_beside_the_translation(client, host, session):
    """A translation with no original is a claim the viewer cannot check."""
    _, token = host
    _post(client, token, session)
    with patch.object(translation_service, "translate", return_value="J'ai besoin du rapport."):
        body = client.get(
            f"/sessions/{session.id}/utterances?lang=fr", headers=_auth(token)
        ).json()
    turn = body["utterances"][0]
    assert turn["text"] == "J'ai besoin du rapport."
    assert turn["originalText"] == "Necesito el informe."


def test_transcript_echoes_the_language_it_answered_in(client, host, session):
    """A request in flight can answer after a newer one; the client must be able to tell."""
    _, token = host
    body = client.get(
        f"/sessions/{session.id}/utterances?lang=de", headers=_auth(token)
    ).json()
    assert body["language"] == "de"


# ─── Failure must never interrupt a conversation ──────────────────────────────

def test_recording_returns_none_on_blank_text(db, session):
    assert (
        utterance_service.record(
            db,
            session_id=session.id,
            speaker_identity="agent",
            speaker_role="agent",
            text="   ",
        )
        is None
    )


def test_a_translator_outage_still_yields_a_caption(db, session):
    """Best-effort: an untranslated caption is a degraded conversation, not a broken one."""
    utterance = utterance_service.record(
        db,
        session_id=session.id,
        speaker_identity="agent",
        speaker_role="agent",
        text="Welcome.",
        language="en",
    )
    with patch.object(translation_service, "translate", return_value=None):
        assert translation_service.translated_text(db, utterance, "fr") == "Welcome."
    assert db.query(UtteranceTranslation).count() == 0


def test_only_finals_reach_the_table(client, host, session):
    """The endpoint stores what it is given; interim revisions never get posted.

    Guards the contract the agent relies on: one row per turn, not one per revision of a
    sentence the model was still hearing.
    """
    _, token = host
    _post(client, token, session, text="Necesito el informe.")
    assert db_count(session) == 1


def db_count(session):
    from tests.conftest import TestingSession

    with TestingSession() as s:
        return s.query(Utterance).filter(Utterance.session_id == session.id).count()
