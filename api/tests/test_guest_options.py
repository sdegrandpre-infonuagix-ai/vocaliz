"""The three options, on the screen a guest actually joins from (Story 10.4 / FR35, FR42).

Story 8.4 settled what happens when somebody chooses: the table, the upward-only host override,
the credit that is spent before money is asked for. What it never grew was a way to *ask* — the
model and `participation.join_options` had no HTTP surface at all, so the join screen had
nothing to call. This is that surface.

Three things are chosen, not one: the tier, whether video is on, and whether to top up. They
arrive together because they are answered together, on one screen, before entering.

The host paying is the single case where nobody is asked. Putting a budget question in front of
somebody who is not spending anything is a question with no meaning, and the override only ever
moves upward — a host able to lower a guest's existing choice would be a host quietly
downgrading them, which is what this epic exists to prevent.
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.models.invitation import Invitation
from src.models.participant_options import ParticipantOptions
from src.models.salon import Salon
from src.models.user import User


@pytest.fixture
def host(db):
    user = User(email="optionshost@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _salon(db, host_user, *, host_pays=False, status="active"):
    row = Salon(
        host_user_id=host_user.id,
        livekit_room_name=f"salon-opts-{host_pays}-{status}",
        source_type="url",
        source_content="c",
        status=status,
        host_pays_all=host_pays,
        participant_cap=6,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _invite(db, salon, host_user, *, token, email="guest@example.com", status="pending"):
    row = Invitation(
        salon_id=salon.id,
        host_user_id=host_user.id,
        guest_email=email,
        guest_phone="",
        invitation_type="email_contact",
        join_token=token,
        status=status,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(row)
    db.commit()
    return row


def _choose(client, token, **body):
    return client.post(f"/invitations/guest-join/{token}/options", json=body)


# ── Choosing ──────────────────────────────────────────────────────────────────


def test_a_guest_chooses_their_own_tier(client, db, host):
    salon = _salon(db, host)
    _invite(db, salon, host, token="opt-a")

    resp = _choose(client, "opt-a", tier="Mode A")

    assert resp.status_code == 200
    assert resp.json()["tier"] == "Mode A"


def test_the_choice_is_recorded_against_this_salon_and_this_person(client, db, host):
    """Keyed on the pair, since somebody may want Mode C for a client call and Base for a
    chat with a friend."""
    salon = _salon(db, host)
    _invite(db, salon, host, token="opt-b", email="chooser@example.com")

    _choose(client, "opt-b", tier="Mode C")

    row = db.query(ParticipantOptions).one()
    assert row.salon_id == salon.id
    assert row.tier == "Mode C"


def test_video_and_a_top_up_travel_with_the_tier(client, db, host):
    """Three answers to one screen. Splitting them into three calls would let somebody enter
    having answered two."""
    salon = _salon(db, host)
    _invite(db, salon, host, token="opt-c")

    body = _choose(client, "opt-c", tier="Base", video=True, topUpCents=1000).json()

    assert body["video"] is True
    assert body["topUpCents"] == 1000
    assert db.query(ParticipantOptions).one().video is True


def test_saying_nothing_is_the_cheapest_tier(client, db, host):
    """Base is where somebody who chose nothing lands — never the most expensive."""
    salon = _salon(db, host)
    _invite(db, salon, host, token="opt-d")

    assert _choose(client, "opt-d").json()["tier"] == "Base"


def test_changing_the_answer_replaces_it(client, db, host):
    """A second row for one pair would leave two answers to "what did they choose", and
    nothing to say which is current."""
    salon = _salon(db, host)
    _invite(db, salon, host, token="opt-e")

    _choose(client, "opt-e", tier="Base")
    _choose(client, "opt-e", tier="Mode A")

    assert db.query(ParticipantOptions).count() == 1
    assert db.query(ParticipantOptions).one().tier == "Mode A"


def test_an_unknown_tier_is_refused(client, db, host):
    """Named rather than coerced to Base. Somebody sending "Mode D" has a client that
    disagrees with the server about what exists, and a silent downgrade hides it."""
    salon = _salon(db, host)
    _invite(db, salon, host, token="opt-f")

    resp = _choose(client, "opt-f", tier="Mode D")

    assert resp.status_code == 400
    assert "Mode D" in resp.json()["detail"]


# ── When the host is paying ───────────────────────────────────────────────────


def test_nobody_is_asked_to_choose_when_the_host_pays(client, db, host):
    """Asking somebody to pick a budget they are not spending is a question with no
    meaning."""
    salon = _salon(db, host, host_pays=True)
    _invite(db, salon, host, token="opt-g")

    body = _choose(client, "opt-g").json()

    assert body["choiceOffered"] is False
    assert body["paymentRequired"] is False


def test_the_host_offer_only_ever_moves_upward(client, db, host):
    """A host able to lower an existing choice would be quietly downgrading their guest."""
    salon = _salon(db, host, host_pays=True)
    _invite(db, salon, host, token="opt-h")

    body = _choose(client, "opt-h", tier="Mode C").json()

    assert body["tier"] == "Mode C"


def test_a_guest_who_chose_nothing_lands_at_mode_b_when_covered(client, db, host):
    """Not Mode A, and the difference is not the price: somebody whose participation is a
    gift should not also be the product being sold to."""
    salon = _salon(db, host, host_pays=True)
    _invite(db, salon, host, token="opt-i")

    assert _choose(client, "opt-i").json()["tier"] == "Mode B"


# ── The screen knows before it asks ───────────────────────────────────────────


def test_the_join_response_says_whether_a_choice_is_offered(client, db, host):
    """The page has to know before it renders. Asking and then hiding the answer would be a
    question somebody watched appear and vanish."""
    salon = _salon(db, host, host_pays=True)
    _invite(db, salon, host, token="opt-j")

    body = client.get("/invitations/guest-join/opt-j").json()

    assert body["hostPaysAll"] is True


def test_an_ordinary_salon_offers_the_choice(client, db, host):
    salon = _salon(db, host)
    _invite(db, salon, host, token="opt-k")

    assert client.get("/invitations/guest-join/opt-k").json()["hostPaysAll"] is False


# ── The same refusals as every other door ─────────────────────────────────────


def test_an_unknown_link_chooses_nothing(client):
    assert _choose(client, "no-such-link", tier="Base").status_code == 404


def test_a_link_to_an_ended_salon_chooses_nothing(client, db, host):
    """Options for a conversation that is over would be a row nobody can act on, recorded
    after the only moment it could have mattered."""
    salon = _salon(db, host)
    _invite(db, salon, host, token="opt-l", status="expired")

    assert _choose(client, "opt-l", tier="Base").status_code == 410
    assert db.query(ParticipantOptions).count() == 0


def test_choosing_needs_no_account_of_its_own(client, db, host):
    """The invitation carries the identifier (Story 10.1), so the person is resolved from it
    rather than from a session the guest does not have."""
    salon = _salon(db, host)
    _invite(db, salon, host, token="opt-m", email="Resolved@Example.COM")

    _choose(client, "opt-m", tier="Base")

    person = db.query(User).filter(User.email == "resolved@example.com").one()
    assert db.query(ParticipantOptions).one().user_id == person.id
