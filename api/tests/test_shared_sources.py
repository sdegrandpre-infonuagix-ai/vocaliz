"""The consented corpus: what gets in, what cannot, and how a spoken question finds it."""
from datetime import datetime, timedelta, timezone

import pytest

from src.models.session import SessionModel
from src.models.shared_source import SharedSource, SharedSourceConsent
from src.models.user import User
from src.services import content_service, shared_source_service
from src.services.jwt_service import issue_token

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def _host(db, email):
    u = User(email=email)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _session(db, user, room="salon-corpus"):
    s = SessionModel(
        host_user_id=user.id,
        livekit_room_name=room,
        source_type="url",
        source_content="c",
        status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture
def alice(db):
    user = _host(db, "alice@example.com")
    return user, _session(db, user, "salon-alice"), issue_token(str(user.id))


def _publish(db, user, session, **overrides):
    fields = {
        "session_id": session.id,
        "shared_by": user.email,
        "url": "https://news.example/iran-usa",
        "summary": "Tensions between the United States and Iran escalated this week.",
        "content": "Full article text about the conflict and its consequences.",
        "topics": ["usa", "iran", "conflict"],
    }
    fields.update(overrides)
    return shared_source_service.publish(db, **fields)


# ─── What can get in ──────────────────────────────────────────────────────────

def test_a_url_is_published(db, alice):
    user, session, _ = alice
    row = _publish(db, user, session)
    assert row is not None
    assert db.query(SharedSource).count() == 1


def test_publishing_records_a_consent(db, alice):
    """The page and the permission are separate rows, because consent belongs to a person."""
    user, session, _ = alice
    row = _publish(db, user, session)
    consent = db.get(SharedSourceConsent, (row.id, user.email))
    assert consent is not None
    assert consent.session_id == session.id


def test_publish_refuses_a_page_with_no_url(db, alice):
    """Structural, not a rule: there is no parameter for a file and no column to hold one."""
    user, session, _ = alice
    assert _publish(db, user, session, url="") is None
    assert db.query(SharedSource).count() == 0


def test_publish_refuses_a_page_with_nothing_to_say(db, alice):
    """A row with neither summary nor text would be found by a search and then be mute."""
    user, session, _ = alice
    assert _publish(db, user, session, summary="", content="") is None


def test_the_model_has_no_way_to_hold_a_file(db):
    """Guards the property that makes uploaded documents unpublishable.

    If a filename or a source type ever appears here, a future caller can publish a
    private document by passing the wrong argument. The absence is the safety.
    """
    columns = set(SharedSource.__table__.columns.keys())
    assert "filename" not in columns
    assert "source_type" not in columns


# ─── Duplicates, and whose consent counts ─────────────────────────────────────

def test_the_same_article_is_one_row(db, alice):
    """Deduplicated on the text, not the address: two URLs can serve one article."""
    user, session, _ = alice
    _publish(db, user, session)
    _publish(db, user, session, url="https://mirror.example/same-story")
    assert db.query(SharedSource).count() == 1


def test_a_second_host_adds_a_consent_not_a_copy(db, alice):
    user, session, _ = alice
    first = _publish(db, user, session)

    bob = _host(db, "bob@example.com")
    bob_session = _session(db, bob, "salon-bob")
    second = _publish(db, bob, bob_session)

    assert second.id == first.id
    assert db.query(SharedSource).count() == 1
    assert db.query(SharedSourceConsent).count() == 2


def test_sharing_prevails_when_one_host_withdraws(db, alice):
    """The point of separating consent from the page: one host taking theirs back must not
    revoke a permission the other never withdrew."""
    user, session, _ = alice
    row = _publish(db, user, session)
    bob = _host(db, "bob@example.com")
    _publish(db, bob, _session(db, bob, "salon-bob"))

    assert shared_source_service.withdraw(db, shared_by=user.email, source_id=row.id)
    assert db.query(SharedSource).count() == 1, "still published by bob"
    assert db.query(SharedSourceConsent).count() == 1


def test_the_page_goes_with_the_last_consent(db, alice):
    """Consent withdrawn has to mean the material is gone, not hidden behind a condition."""
    user, session, _ = alice
    row = _publish(db, user, session)
    assert shared_source_service.withdraw(db, shared_by=user.email, source_id=row.id)
    assert db.query(SharedSource).count() == 0


def test_withdrawing_someone_elses_consent_does_nothing(db, alice):
    user, session, _ = alice
    row = _publish(db, user, session)
    assert not shared_source_service.withdraw(
        db, shared_by="stranger@example.com", source_id=row.id
    )
    assert db.query(SharedSource).count() == 1


def test_republishing_refreshes_the_recency(db, alice):
    """A page somebody brings up again today is topical again today."""
    user, session, _ = alice
    row = _publish(db, user, session)
    row.last_shared_at = NOW - timedelta(days=90)
    db.commit()

    bob = _host(db, "bob@example.com")
    _publish(db, bob, _session(db, bob, "salon-bob"))
    db.expire_all()
    # Compared naive: SQLite does not keep the offset, so a value read back has no tzinfo
    # even though the column is declared with one.
    refreshed = db.get(SharedSource, row.id).last_shared_at
    assert refreshed.replace(tzinfo=None) > (NOW - timedelta(days=1)).replace(tzinfo=None)


# ─── Finding it from a spoken question ────────────────────────────────────────

def test_a_spoken_question_reaches_the_page(db, alice):
    """The case that motivated all of this: asking about a subject a different host
    supplied material on."""
    user, session, _ = alice
    _publish(db, user, session)
    results = shared_source_service.search(db, "what is the latest on the USA and Iran")
    assert len(results) == 1
    assert "Iran" in results[0]["summary"]


def test_an_unrelated_question_finds_nothing(db, alice):
    user, session, _ = alice
    _publish(db, user, session)
    assert shared_source_service.search(db, "bread baking sourdough") == []


def test_topics_outweigh_the_prose(db, alice):
    """Topics are the terms a person would say out loud, so a hit there is worth more."""
    user, session, _ = alice
    _publish(db, user, session, topics=["nuclear"], content="A", summary="Something else.")
    _publish(
        db,
        user,
        session,
        url="https://other.example/b",
        topics=[],
        content="B",
        summary="A passing mention of nuclear matters.",
    )
    results = shared_source_service.search(db, "nuclear")
    assert results[0]["topics"] == ["nuclear"]


def test_the_article_date_decides_recency_not_the_paste_date(db, alice):
    """An old article shared today must not rank as fresh. This is the whole reason
    article_date exists."""
    user, session, _ = alice
    old = _publish(db, user, session, url="https://a.example/old", content="Old text.")
    old.article_date = NOW - timedelta(days=400)
    fresh = _publish(db, user, session, url="https://b.example/new", content="New text.")
    fresh.article_date = NOW - timedelta(days=1)
    db.commit()

    results = shared_source_service.search(db, "usa iran conflict")
    assert results[0]["sourceId"] == str(fresh.id)


def test_results_carry_their_attribution(db, alice):
    """An agent about to read a summary aloud should be able to say where it came from."""
    user, session, _ = alice
    row = _publish(db, user, session)
    row.author = "Marie Tremblay"
    row.publisher = "Le Devoir"
    db.commit()
    result = shared_source_service.search(db, "iran")[0]
    assert result["author"] == "Marie Tremblay"
    assert result["publisher"] == "Le Devoir"


def test_excerpts_come_from_the_stored_text(db, alice):
    """Not re-fetched: the page may have changed or gone, and the honest answer is the one
    the salon actually read."""
    user, session, _ = alice
    row = _publish(
        db, user, session, content="The treaty was signed in Geneva on a Tuesday morning."
    )
    found = shared_source_service.excerpts(db, row.id, "treaty Geneva signed")
    assert found and "Geneva" in found[0]


# ─── Through the API ──────────────────────────────────────────────────────────

def test_search_requires_a_token(client):
    """Shared between hosts, not with the internet. An open endpoint over uploaded
    material would be a crawlable index of it."""
    assert client.get("/sources/search?q=iran").status_code == 401


def test_search_returns_results_to_a_signed_in_host(client, db, alice):
    user, session, token = alice
    _publish(db, user, session)
    body = client.get(
        "/sources/search?q=iran usa", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert len(body["results"]) == 1


def test_a_host_can_list_and_withdraw_their_own(client, db, alice):
    """Consent that cannot be reviewed is not consent."""
    user, session, token = alice
    row = _publish(db, user, session)
    auth = {"Authorization": f"Bearer {token}"}

    listed = client.get("/sources/mine", headers=auth).json()
    assert [s["sourceId"] for s in listed["sources"]] == [str(row.id)]

    assert client.delete(f"/sources/{row.id}", headers=auth).status_code == 200
    assert client.get("/sources/mine", headers=auth).json()["sources"] == []


def test_withdrawing_a_page_you_did_not_publish_is_a_404(client, db, alice):
    """404 rather than 403: whether an id exists in the corpus is not something one host
    needs to learn about another."""
    user, session, _ = alice
    row = _publish(db, user, session)
    stranger = _host(db, "stranger@example.com")
    response = client.delete(
        f"/sources/{row.id}",
        headers={"Authorization": f"Bearer {issue_token(str(stranger.id))}"},
    )
    assert response.status_code == 404


# ─── Provenance read off the page ─────────────────────────────────────────────

def test_an_iso_date_is_parsed():
    parsed = content_service.parse_article_date("2026-08-01T14:30:00Z")
    assert parsed is not None and parsed.year == 2026


def test_a_prose_date_is_no_date():
    """Guessing a day/month order would be wrong half the year. NULL is the honest answer."""
    assert content_service.parse_article_date("August 1st, 2026") is None
    assert content_service.parse_article_date("") is None


def test_a_naive_date_is_read_as_utc():
    parsed = content_service.parse_article_date("2026-08-01T14:30:00")
    assert parsed is not None and parsed.tzinfo is not None


def test_metadata_falls_back_to_the_host_name():
    """What a person would say anyway — "I read it on lemonde.fr" — and never wrong, only
    uninformative."""
    meta = content_service.extract_metadata("<html></html>", "https://www.lemonde.fr/a")
    assert meta["publisher"] == "lemonde.fr"


# ─── Ten topics, in English, and the billboard ────────────────────────────────

def test_topics_are_capped_at_ten():
    """The extractor asks for ten; the ceiling is what holds if a model ignores it."""
    from src.services import summary_service

    assert summary_service.MAX_TOPICS == 10
    many = [f"topic{i}" for i in range(30)]
    assert len(summary_service.normalise_topics(many)) == 10


def test_fewer_than_ten_is_accepted():
    """A thin page has fewer topics, and padding to reach a count would make it findable by
    questions it cannot answer."""
    from src.services import summary_service

    assert summary_service.normalise_topics(["iran", "usa"]) == ["iran", "usa"]


def test_the_extractor_asks_for_english_only():
    """One vocabulary for the corpus is what lets a question in any language be matched
    against every page — a corpus half in French would make the translation useless."""
    from src.services import summary_service

    assert "Write them in English, always" in summary_service._TOPICS_PROMPT
    assert "exactly ten" in summary_service._TOPICS_PROMPT


def test_a_french_question_reaches_an_english_topic(db, alice):
    """The reason every question is translated: "guerre" does not contain "war"."""
    from unittest.mock import patch

    from src.services import translation_service

    user, session, _ = alice
    _publish(
        db,
        user,
        session,
        topics=["war", "iran", "united states"],
        summary="An English summary of the conflict.",
        content="English body text.",
    )

    # Untranslated, the French words match nothing.
    with patch.object(translation_service, "translate", return_value=None):
        assert shared_source_service.search(db, "la guerre entre les États-Unis") == []

    # Translated, they reach it.
    with patch.object(
        translation_service, "translate", return_value="the war between the United States"
    ):
        assert len(shared_source_service.search(db, "la guerre entre les États-Unis")) == 1


def test_the_original_words_still_count(db, alice):
    """A union, not a replacement: a translator that mangles a proper noun must not cost the
    match the untranslated question would have made."""
    from unittest.mock import patch

    from src.services import translation_service

    user, session, _ = alice
    _publish(db, user, session, topics=["iran"], summary="About Iran.", content="Body.")

    with patch.object(translation_service, "translate", return_value="the country of Persia"):
        assert len(shared_source_service.search(db, "Iran")) == 1


# ─── The billboard ────────────────────────────────────────────────────────────

def test_the_billboard_counts_pages_not_mentions(db, alice):
    """The question is how many pages are about a subject, not how often a word appears."""
    user, session, _ = alice
    _publish(db, user, session, topics=["iran", "iran", "usa"], content="A")
    _publish(db, user, session, url="https://b.example/b", topics=["iran"], content="B")

    tally = {t["topic"]: t["pages"] for t in shared_source_service.top_topics(db)}
    assert tally == {"iran": 2, "usa": 1}


def test_the_billboard_is_ordered_by_popularity(db, alice):
    user, session, _ = alice
    _publish(db, user, session, topics=["rare"], content="A")
    for i in range(3):
        _publish(db, user, session, url=f"https://x{i}.example/", topics=["common"], content=f"B{i}")

    assert [t["topic"] for t in shared_source_service.top_topics(db)] == ["common", "rare"]


def test_the_billboard_is_empty_when_nothing_is_published(db):
    """An empty billboard says less than none, so the page hides it — but the endpoint has
    to say so rather than fail."""
    assert shared_source_service.top_topics(db) == []


def test_the_billboard_needs_no_token(client):
    """It shows at the top of the host page before anyone signs in."""
    assert client.get("/sources/topics").status_code == 200


def test_the_billboard_exposes_no_addresses(client, db, alice):
    """Subject words and counts only. No URLs, no summaries, and nothing from a private
    source — shared_sources holds only what a host published."""
    user, session, _ = alice
    _publish(db, user, session)
    body = client.get("/sources/topics").json()
    assert body["topics"]
    for entry in body["topics"]:
        assert set(entry) == {"topic", "pages"}
