"""One link per guest, good once, dead when the Salon is (Story 10.3, extending FR5).

Mostly inherited and verified here rather than rebuilt. `invitations.join_token` is unique per
invitation, `status` moves to accepted the moment a guest is genuinely present, and
`finalize_salon` expires whatever was never used. What this file does is check the three claims
end to end, because "a link is single-use" is the kind of property that is true until one path
forgets to ask.

The distinction that turns out to matter is between a link that was **used** and one that was
**abandoned**. Both are refused, and telling somebody the wrong one is not a cosmetic problem:
a guest who never opened their invitation, reading that it has already been used, has been told
that somebody else got in with their link. That is an accusation, not an error message, and the
support call it produces is about a security incident that did not happen.
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.salon_event import SalonEvent
from src.models.user import User
from src.services.jwt_service import issue_token


@pytest.fixture
def host(db):
    user = User(email="linkhost@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, issue_token(str(user.id))


@pytest.fixture
def salon(db, host):
    host_user, _ = host
    row = Salon(
        host_user_id=host_user.id,
        livekit_room_name="salon-links",
        source_type="url",
        source_content="c",
        status="active",
        participant_cap=6,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _invite(db, salon, host_user, *, token, email=None, status="pending", hours=24):
    row = Invitation(
        salon_id=salon.id,
        host_user_id=host_user.id,
        guest_email=email or f"{token}@example.com",
        guest_phone="",
        invitation_type="email_contact",
        join_token=token,
        status=status,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=hours),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ── One link each ─────────────────────────────────────────────────────────────


def test_each_guest_gets_a_link_of_their_own(client, salon, host, db):
    """Extends FR5. Two guests are two invitations, and nothing about the first is reusable
    by the second."""
    _, token = host

    first = client.post(
        f"/salons/{salon.id}/invitations",
        json={"guestEmail": "one@example.com"},
        headers=_auth(token),
    )
    second = client.post(
        f"/salons/{salon.id}/invitations",
        json={"guestEmail": "two@example.com"},
        headers=_auth(token),
    )

    assert first.status_code == second.status_code == 201
    tokens = {row.join_token for row in db.query(Invitation).all()}
    assert len(tokens) == 2


def test_two_invitations_do_not_share_a_telephone_code(client, salon, host, db):
    """A shared code would put a caller in whichever room the dispatcher happened to match."""
    _, token = host
    for address in ("one@example.com", "two@example.com"):
        client.post(
            f"/salons/{salon.id}/invitations",
            json={"guestEmail": address},
            headers=_auth(token),
        )

    pins = [row.phone_pin for row in db.query(Invitation).all() if row.phone_pin]

    assert len(pins) == len(set(pins))


def test_a_second_invitation_to_the_same_address_reuses_the_link(client, salon, host, db):
    """Not a fourth link for one person. Inviting the same address twice within a few
    minutes is a host saying the first one did not arrive, so the same link is mailed
    again — one guest, one link, however many times it is sent."""
    _, token = host
    first = client.post(
        f"/salons/{salon.id}/invitations",
        json={"guestEmail": "again@example.com"},
        headers=_auth(token),
    ).json()
    second = client.post(
        f"/salons/{salon.id}/invitations",
        json={"guestEmail": "again@example.com"},
        headers=_auth(token),
    ).json()

    assert first["invitationId"] == second["invitationId"]
    assert db.query(Invitation).count() == 1


# ── Good once ─────────────────────────────────────────────────────────────────


def test_a_link_works_until_it_is_spent(client, salon, host, db):
    host_user, _ = host
    _invite(db, salon, host_user, token="lnk-fresh")

    assert client.get("/invitations/guest-join/lnk-fresh").status_code == 200


def test_a_link_is_spent_when_the_guest_is_really_in(client, salon, host, db):
    """At the microphone, not at the page load. A guest whose browser refuses the microphone
    can reopen the link elsewhere rather than burning it on a page they cannot speak from."""
    host_user, _ = host
    _invite(db, salon, host_user, token="lnk-spend")

    client.post("/invitations/guest-join/lnk-spend/confirm")

    assert client.get("/invitations/guest-join/lnk-spend").status_code == 410


def test_a_used_link_says_it_was_used(client, salon, host, db):
    host_user, _ = host
    _invite(db, salon, host_user, token="lnk-used", status="accepted")

    detail = client.get("/invitations/guest-join/lnk-used").json()["detail"]

    assert "used" in detail.lower()


def test_an_expired_link_is_refused(client, salon, host, db):
    host_user, _ = host
    _invite(db, salon, host_user, token="lnk-old", hours=-1)

    assert client.get("/invitations/guest-join/lnk-old").status_code == 410


def test_an_unknown_link_is_not_found(client):
    assert client.get("/invitations/guest-join/nothing-like-it").status_code == 404


# ── Dead when the Salon is ────────────────────────────────────────────────────


def test_ending_the_salon_closes_the_links_nobody_used(client, salon, host, db):
    """The acceptance criterion. An invitation left pending also holds its telephone code
    under a partial unique index, so leaving it open drains the pool one Salon at a time."""
    from src.services import salon_lifecycle

    host_user, _ = host
    _invite(db, salon, host_user, token="lnk-unused")

    salon_lifecycle.finalize_salon(salon, db)

    assert db.query(Invitation).filter(
        Invitation.join_token == "lnk-unused"
    ).one().status == "expired"


def test_a_link_to_an_ended_salon_no_longer_works(client, salon, host, db):
    from src.services import salon_lifecycle

    host_user, _ = host
    _invite(db, salon, host_user, token="lnk-after")
    salon_lifecycle.finalize_salon(salon, db)

    assert client.get("/invitations/guest-join/lnk-after").status_code == 410


def test_an_abandoned_link_is_not_reported_as_used(client, salon, host, db):
    """A guest who never opened their invitation, told it has already been used, has been
    told somebody else got in with their link. That is an accusation rather than an error,
    and the support call it produces is about an incident that did not happen."""
    from src.services import salon_lifecycle

    host_user, _ = host
    _invite(db, salon, host_user, token="lnk-abandoned")
    salon_lifecycle.finalize_salon(salon, db)

    detail = client.get("/invitations/guest-join/lnk-abandoned").json()["detail"]

    assert "used" not in detail.lower()


def test_confirming_an_abandoned_link_does_not_record_a_participation(client, salon, host, db):
    """Confirmation is idempotent so a retry cannot throw somebody out — but idempotent for
    a guest who is *in*. Somebody arriving after the Salon closed was never in it, and
    recording them would put a participant in a conversation that had ended."""
    from src.services import salon_lifecycle

    host_user, _ = host
    _invite(db, salon, host_user, token="lnk-late")
    salon_lifecycle.finalize_salon(salon, db)
    before = db.query(SalonEvent).count()

    resp = client.post("/invitations/guest-join/lnk-late/confirm")

    assert resp.status_code == 410
    assert db.query(SalonEvent).count() == before


def test_confirming_twice_still_does_not_throw_a_guest_out(client, salon, host, db):
    """The reason confirmation is idempotent in the first place, unchanged: a retry or a lost
    response must not remove somebody who is already in the room."""
    host_user, _ = host
    _invite(db, salon, host_user, token="lnk-retry")

    client.post("/invitations/guest-join/lnk-retry/confirm")
    again = client.post("/invitations/guest-join/lnk-retry/confirm")

    assert again.status_code == 200
