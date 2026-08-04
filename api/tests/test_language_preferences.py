"""The two languages a person chose, remembered on their account.

Both used to live in the browser's local storage, so a host who set the interface to Polish on
a laptop met English again on their phone. A choice follows the person; the language they were
first heard speaking belongs to the participation and stays there.

The distinction this file exists to protect: for captions, the empty string is a real choice —
"as spoken", translate nothing — and NULL means never chosen. Collapse them and it becomes
impossible to offer a default without overriding a decision somebody made on purpose.
"""
import pytest

from src.models.user import User


@pytest.fixture
def person(db, client):
    """A signed-in user and their bearer token."""
    from src.services.jwt_service import issue_token

    user = User(email="reader@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, {"Authorization": f"Bearer {issue_token(str(user.id))}"}


def _patch(client, auth, **body):
    return client.patch("/me/preferences", json=body, headers=auth)


# ─── Saving ──────────────────────────────────────────────────────────────────

def test_the_interface_choice_is_remembered(client, person, db):
    user, auth = person
    assert _patch(client, auth, interfaceLanguage="pl").status_code == 200
    db.refresh(user)
    assert user.interface_language == "pl"


def test_the_caption_choice_is_remembered(client, person, db):
    user, auth = person
    assert _patch(client, auth, captionLanguage="th").status_code == 200
    db.refresh(user)
    assert user.caption_language == "th"


def test_as_spoken_is_saved_rather_than_ignored(client, person, db):
    """The empty string is the "as spoken" option. Treating it as "nothing to save" would
    discard a real decision every time somebody chose not to be translated."""
    user, auth = person
    _patch(client, auth, captionLanguage="th")
    assert _patch(client, auth, captionLanguage="").status_code == 200
    db.refresh(user)
    assert user.caption_language == ""


def test_never_chosen_stays_null(client, person, db):
    """Null and empty are different answers, and the clients read them differently: null falls
    back to the browser language, empty means translate nothing."""
    user, auth = person
    db.refresh(user)
    assert user.interface_language is None
    assert user.caption_language is None


def test_sending_one_preference_leaves_the_other_alone(client, person, db):
    """Two separate controls on screen. A request that touched both would let the last one
    clicked erase the other."""
    user, auth = person
    _patch(client, auth, interfaceLanguage="uk", captionLanguage="sv")
    _patch(client, auth, interfaceLanguage="he")
    db.refresh(user)
    assert user.interface_language == "he"
    assert user.caption_language == "sv", "the caption choice was collateral damage"


def test_both_can_be_set_at_once(client, person, db):
    user, auth = person
    _patch(client, auth, interfaceLanguage="ta", captionLanguage="ml")
    db.refresh(user)
    assert (user.interface_language, user.caption_language) == ("ta", "ml")


def test_the_response_carries_the_new_values(client, person):
    _, auth = person
    body = _patch(client, auth, interfaceLanguage="ka", captionLanguage="am").json()
    assert body["interfaceLanguage"] == "ka"
    assert body["captionLanguage"] == "am"


# ─── Reading ─────────────────────────────────────────────────────────────────

def test_the_profile_returns_both_preferences(client, person, db):
    user, auth = person
    user.interface_language = "sw"
    user.caption_language = ""
    db.commit()
    body = client.get("/me/profile", headers=auth).json()
    assert body["interfaceLanguage"] == "sw"
    assert body["captionLanguage"] == "", "as-spoken must survive the round trip"


def test_the_profile_distinguishes_never_chosen_from_as_spoken(client, person):
    _, auth = person
    assert client.get("/me/profile", headers=auth).json()["captionLanguage"] is None


# ─── What this must not disturb ──────────────────────────────────────────────

def test_a_preference_is_not_the_language_that_was_heard(client, person, db):
    """detected_language is written by the agent from speech; these two are decisions. Merging
    them would make it impossible to tell which had set the value — and a host who reads Polish
    while speaking French is an ordinary person, not a contradiction."""
    user, auth = person
    user.detected_language = "fr"
    db.commit()
    _patch(client, auth, interfaceLanguage="pl", captionLanguage="pl")
    db.refresh(user)
    assert user.detected_language == "fr"


def test_the_agent_endpoint_does_not_touch_the_preferences(client, person, db):
    user, auth = person
    _patch(client, auth, interfaceLanguage="pl")
    client.patch("/me/language", json={"language": "fr"}, headers=auth)
    db.refresh(user)
    assert user.detected_language == "fr"
    assert user.interface_language == "pl"


# ─── Refusals ────────────────────────────────────────────────────────────────

def test_a_stranger_cannot_set_a_preference(client):
    assert client.patch("/me/preferences", json={"interfaceLanguage": "pl"}).status_code in (
        401,
        403,
    )


@pytest.mark.parametrize("bad", ["<script>", "a" * 20, "12", "en_CA!"])
def test_nonsense_is_refused(client, person, bad):
    _, auth = person
    assert _patch(client, auth, interfaceLanguage=bad).status_code == 422


def test_a_refused_value_changes_nothing(client, person, db):
    user, auth = person
    _patch(client, auth, interfaceLanguage="ro")
    _patch(client, auth, interfaceLanguage="!!!")
    db.refresh(user)
    assert user.interface_language == "ro"


# ─── Caption size ────────────────────────────────────────────────────────────
#
# Stored as a whole percentage rather than a multiplier. The client compares the stored value
# against a fixed list of steps, and a float read back from a database is not reliably the
# float in that list.

def test_the_caption_size_is_remembered(client, person, db):
    user, auth = person
    assert _patch(client, auth, captionScale=145).status_code == 200
    db.refresh(user)
    assert user.caption_scale == 145


def test_never_chosen_leaves_the_device_alone(client, person):
    """null rather than a default, so first sign-in does not jump somebody to a size they
    never asked for — the device keeps whatever it had."""
    _, auth = person
    assert client.get("/me/profile", headers=auth).json()["captionScale"] is None


def test_a_size_survives_the_round_trip(client, person):
    _, auth = person
    _patch(client, auth, captionScale=85)
    assert client.get("/me/profile", headers=auth).json()["captionScale"] == 85


def test_a_size_does_not_disturb_the_languages(client, person, db):
    user, auth = person
    _patch(client, auth, interfaceLanguage="uk", captionLanguage="")
    _patch(client, auth, captionScale=175)
    db.refresh(user)
    assert user.interface_language == "uk"
    assert user.caption_language == "", "as-spoken was collateral damage"
    assert user.caption_scale == 175


@pytest.mark.parametrize("bad", [0, 10, 400, -100])
def test_an_unreadable_size_is_refused(client, person, bad):
    """Bounded on purpose: a percentage outside a readable range would leave somebody with a
    caption panel they cannot use and no obvious way back."""
    _, auth = person
    assert _patch(client, auth, captionScale=bad).status_code == 422


def test_a_refused_size_changes_nothing(client, person, db):
    user, auth = person
    _patch(client, auth, captionScale=120)
    _patch(client, auth, captionScale=9999)
    db.refresh(user)
    assert user.caption_scale == 120


def test_the_database_refuses_what_the_schema_would_have(client, person, db):
    """The CHECK is declared on the model as well as in the migration. A constraint that lives
    only in a migration is invisible to this test database, which is how an unmet CHECK reached
    production earlier tonight."""
    import sqlalchemy

    user, _ = person
    user.caption_scale = 5000
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.commit()
    db.rollback()
