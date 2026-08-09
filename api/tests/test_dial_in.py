"""Joining a Salon by six-digit code, the way somebody on a telephone would.

The codes have existed since migration 022 — minted for every invitation, reserved in a pool,
released when the Salon ends — and nothing could redeem one. There is no SIP trunk and no
dispatch rule, so the telephone leg they were built for does not exist; /call is the same door
opened from a browser.

Deliberately the same lookup a dialled call will use. What is exercised here is what the
telephone will exercise later, so this is a rehearsal rather than a stand-in.
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.models.invitation import Invitation
from src.models.salon_event import SalonEvent
from src.models.salon import Salon
from src.models.user import User
from src.services import salon_code_service


@pytest.fixture
def salon(db):
    host = User(email="dialhost@example.com")
    db.add(host)
    db.commit()
    db.refresh(host)
    salon = Salon(
        host_user_id=host.id,
        livekit_room_name="salon-dial",
        source_type="url",
        source_content="c",
        status="active",
    )
    db.add(salon)
    db.commit()
    db.refresh(salon)
    return salon


def _invite(db, salon, code, *, token="tok-dial"):
    row = Invitation(
        salon_id=salon.id,
        host_user_id=salon.host_user_id,
        guest_email="caller@example.com",
        guest_phone="",
        invitation_type="email_contact",
        join_token=token,
        phone_pin=code,
        status="pending",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ─── Placing the call ─────────────────────────────────────────────────────────

def test_a_valid_code_hands_out_credentials(client, db, salon):
    code = salon_code_service.claim(db)
    _invite(db, salon, code)

    resp = client.post(f"/invitations/dial/{code}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["livekitRoomName"] == "salon-dial"
    assert body["participantToken"]


def test_an_unknown_code_is_refused(client):
    assert client.post("/invitations/dial/000000").status_code == 404


def test_a_malformed_code_is_refused(client):
    for value in ("12345", "1234567", "abcdef"):
        assert client.post(f"/invitations/dial/{value}").status_code == 404


def test_a_code_reveals_nothing_about_which_salons_exist(client, db, salon):
    """One message for an unknown code and for a code whose Salon is over. Two different
    answers would let anybody sweep the six-digit space and learn which Salons are running."""
    code = salon_code_service.claim(db)
    _invite(db, salon, code)
    salon.status = "ended"
    db.commit()

    over = client.post(f"/invitations/dial/{code}")
    unknown = client.post("/invitations/dial/999999")
    assert over.status_code == unknown.status_code == 404
    assert over.json()["detail"] == unknown.json()["detail"]


def test_an_ended_salon_cannot_be_called(client, db, salon):
    code = salon_code_service.claim(db)
    _invite(db, salon, code)
    salon.status = "ended"
    db.commit()
    assert client.post(f"/invitations/dial/{code}").status_code == 404


# ─── What a dropped call must not cost ────────────────────────────────────────

def test_the_code_survives_the_call(client, db, salon):
    """A telephone call drops. Somebody who has to ask their host for a fresh code because
    the line cut out has been failed by the product, not by the network."""
    code = salon_code_service.claim(db)
    _invite(db, salon, code)

    assert client.post(f"/invitations/dial/{code}").status_code == 200
    assert client.post(f"/invitations/dial/{code}").status_code == 200


def test_calling_does_not_spend_the_join_link(client, db, salon):
    """The link and the code are two ways into the same Salon. Dialling must not consume the
    one the guest might still need in a browser."""
    code = salon_code_service.claim(db)
    invitation = _invite(db, salon, code)

    client.post(f"/invitations/dial/{code}")
    db.refresh(invitation)
    assert invitation.status == "pending"


# ─── What the report sees ─────────────────────────────────────────────────────

def test_a_caller_is_recorded_as_having_no_screen(client, db, salon):
    """It is a browser today. What matters to anyone reading the report is that this person
    had no captions and no controls, and that is true of the simulation exactly as it will be
    of the call."""
    code = salon_code_service.claim(db)
    _invite(db, salon, code)
    client.post(f"/invitations/dial/{code}")

    row = db.query(SalonEvent).filter(SalonEvent.salon_name == "salon-dial").first()
    assert row is not None
    assert row.device_type == "telephone"


def test_the_caller_is_the_person_the_code_was_issued_to(client, db, salon):
    """The code belongs to one invitation, which is what makes a caller identifiable at all —
    a Salon-wide code would put an anonymous voice in the room."""
    code = salon_code_service.claim(db)
    _invite(db, salon, code)
    client.post(f"/invitations/dial/{code}")

    row = db.query(SalonEvent).filter(SalonEvent.salon_name == "salon-dial").first()
    assert row.email == "caller@example.com"


# ─── The page ─────────────────────────────────────────────────────────────────

def test_the_call_page_is_served(client):
    resp = client.get("/call")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_the_caller_is_offered_nothing_a_telephone_lacks(client):
    """No transcript, no language picker, no controls — for the caller.

    Scoped to the dialer rather than the page. The page also carries the clerk's desk, which
    has captions by design; asserting on the whole document would forbid the very thing the
    other half exists to show. A simulation richer than the thing it stands in for tests
    something else, and the thing being simulated here is a telephone."""
    body = client.get("/call").text
    caller = body[body.index('id="dialer"') : body.index("</header>")]
    for absent in ("cap-log", "cap-lang", "caption", "textarea"):
        assert absent not in caller, f"the caller is offered {absent}, which a telephone has not"


# The page's own microphone timing is asserted in test_landing_page, which owns that page.
# It rings the desk directly now; this endpoint remains the door for somebody holding a code,
# which is what a real dialled call will present.


# ─── Ringing the desk from the front page ─────────────────────────────────────
#
# No account, no link, no code: one button opens a Salon in the desk's name, puts the caller
# in it, and mails the desk that somebody is waiting. It is a telephone call minus the
# telephone, and it is public — which is the whole reason these tests exist.

from unittest.mock import AsyncMock, patch  # noqa: E402

from src.config import settings  # noqa: E402


@pytest.fixture
def desk(db):
    user = User(email=settings.front_desk_email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _ring(client):
    with patch("src.services.livekit_service.create_room", new_callable=AsyncMock), patch(
        "src.services.livekit_service.dispatch_agent", new_callable=AsyncMock
    ):
        return client.post("/invitations/call-the-desk?email=caller@example.com")


def test_one_press_puts_the_caller_in_a_room(client, desk):
    resp = _ring(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["participantToken"] and body["livekitRoomName"]


def test_the_salon_belongs_to_the_desk(client, desk, db):
    """Owned by the address that answers, so signing in at the console offers to rejoin it.
    A Salon owned by nobody could not be answered at all."""
    body = _ring(client).json()
    salon = db.query(Salon).filter(
        Salon.livekit_room_name == body["livekitRoomName"]
    ).one()
    assert salon.host_user_id == desk.id


def test_the_desk_is_told_somebody_is_waiting(client, desk, db):
    """The email is the whole notification. Without it a caller sits in a room nobody knows
    about, listening to an agent, until the cap ends the Salon."""
    from src.models.invitation import Invitation

    body = _ring(client).json()
    salon = db.query(Salon).filter(
        Salon.livekit_room_name == body["livekitRoomName"]
    ).one()
    addressed = db.query(Invitation).filter(
        Invitation.salon_id == salon.id,
        Invitation.guest_email == settings.front_desk_email,
    ).all()
    assert len(addressed) == 1


def test_the_caller_gets_an_identity_of_their_own(client, desk, db):
    """Never sent anywhere. It exists so the room can name this person and the report can
    count them — without it a caller is an unattributable voice.

    It carries their identifier since Story 10.1: a link addressed to nobody left nothing to
    hold the ten free minutes against, and ringing again was how somebody got a fresh
    allowance for the price of pressing a button."""
    from src.models.invitation import Invitation

    body = _ring(client).json()
    salon = db.query(Salon).filter(
        Salon.livekit_room_name == body["livekitRoomName"]
    ).one()
    callers = db.query(Invitation).filter(
        Invitation.salon_id == salon.id,
        Invitation.invitation_type == "telephone_caller",
    ).all()
    assert len(callers) == 1
    assert callers[0].guest_email == "caller@example.com"
    assert body["participantIdentity"]


def test_ringing_without_an_identifier_is_refused(client, desk):
    """No account and no code is unchanged; no identifier at all is not. Either channel will
    do and nothing is verified — what it buys is a key to hold the allowance against."""
    from unittest.mock import AsyncMock, patch as _patch

    with _patch("src.services.livekit_service.create_room", new_callable=AsyncMock), _patch(
        "src.services.livekit_service.dispatch_agent", new_callable=AsyncMock
    ):
        resp = client.post("/invitations/call-the-desk")

    assert resp.status_code == 400


def test_a_number_alone_is_enough_to_ring(client, desk, db):
    """Somebody who has a telephone and no address is exactly who this endpoint is for."""
    from unittest.mock import AsyncMock, patch as _patch

    with _patch("src.services.livekit_service.create_room", new_callable=AsyncMock), _patch(
        "src.services.livekit_service.dispatch_agent", new_callable=AsyncMock
    ):
        resp = client.post("/invitations/call-the-desk?phone=%2B15145550123")

    assert resp.status_code == 200
    assert db.query(User).filter(User.phone_number == "+15145550123").count() == 1


def test_ringing_twice_is_one_person(client, desk, db):
    """The whole reason an identifier is required. Two calls are one allowance, not two."""
    from unittest.mock import AsyncMock, patch as _patch

    with _patch("src.services.livekit_service.create_room", new_callable=AsyncMock), _patch(
        "src.services.livekit_service.dispatch_agent", new_callable=AsyncMock
    ):
        client.post("/invitations/call-the-desk?email=twice@example.com")
        client.post("/invitations/call-the-desk?email=Twice@Example.COM")

    assert db.query(User).filter(User.email == "twice@example.com").count() == 1


def test_the_caller_is_recorded_as_having_no_screen(client, desk, db):
    body = _ring(client).json()
    row = db.query(SalonEvent).filter(
        SalonEvent.salon_name == body["livekitRoomName"]
    ).first()
    assert row is not None and row.device_type == "telephone"


def test_an_agent_is_dispatched(client, desk):
    """A caller who reaches a room with nobody in it has reached nothing. The desk may take a
    minute to read its email; the agent is what answers meanwhile."""
    with patch("src.services.livekit_service.create_room", new_callable=AsyncMock), patch(
        "src.services.livekit_service.dispatch_agent", new_callable=AsyncMock
    ) as dispatched:
        client.post("/invitations/call-the-desk?email=caller@example.com")
    assert dispatched.await_count == 1


def test_without_a_desk_account_nothing_is_created(client, db):
    """The account is not minted on the fly: one an anonymous request could create is one
    anybody could create, and this address is the one that reads the reports."""
    assert _ring(client).status_code == 503
    assert db.query(Salon).count() == 0
