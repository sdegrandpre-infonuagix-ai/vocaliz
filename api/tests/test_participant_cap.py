"""How many people fit in a Salon, and who decides (Story 10.2, replacing FR2).

Three is a starting value, never a fact about the product. The multi-rooms topology has one
room and one interpreter per participant, so nothing in it counts to three or to any other
number — the cost of a fourth person is one more interpreter, which is a price question rather
than an architectural one. Build for N, configure at 3.

Which is why the ceiling moves out of the environment and into the persisted settings of Story
7.1: a number somebody will want to raise for one customer, on a Tuesday, without a deploy. The
API reads the same `salon_settings` table the orchestrator writes — one table, two readers, no
second copy to disagree with the first.

A host may ask for fewer than the ceiling and gets what they asked for. Asking for more is
bounded rather than refused: they wanted the biggest Salon available, and the largest available
is what they are given.
"""
import pytest

from src.participant_cap import (
    CEILING_SETTING,
    DEFAULT_CEILING,
    MINIMUM_CAP,
    bounded,
    ceiling,
    is_full,
    room_full_message,
)


def _store(db, value: float) -> None:
    """Write the ceiling the way the orchestrator's settings store does."""
    from sqlalchemy import text

    db.execute(
        text("CREATE TABLE IF NOT EXISTS salon_settings (name VARCHAR(64) PRIMARY KEY, value FLOAT NOT NULL)")
    )
    db.execute(
        text("INSERT INTO salon_settings (name, value) VALUES (:name, :value)"),
        {"name": CEILING_SETTING, "value": value},
    )
    db.flush()


# ── The ceiling, and where it is read from ────────────────────────────────────


def test_three_to_begin_with():
    """A starting value and not a fact about the product."""
    assert DEFAULT_CEILING == 3


def test_the_ceiling_comes_from_the_persisted_settings(db):
    _store(db, 6)

    assert ceiling(db) == 6


def test_a_ceiling_nobody_has_moved_is_the_documented_one(db):
    """Only what somebody actually changed is stored, so a missing row means the default
    applies — the same reading the orchestrator's own store makes of an absent name."""
    assert ceiling(db) == DEFAULT_CEILING


def test_a_new_ceiling_needs_no_deploy(db):
    """The whole reason it left the environment. Read per call rather than at import, so a
    value changed while the service is running is the value the next Salon gets."""
    _store(db, 8)
    assert ceiling(db) == 8

    from sqlalchemy import text

    db.execute(
        text("UPDATE salon_settings SET value = :value WHERE name = :name"),
        {"name": CEILING_SETTING, "value": 4},
    )
    db.flush()

    assert ceiling(db) == 4


def test_a_deployment_with_no_settings_table_still_opens_salons(db):
    """The state of a deployment whose orchestrator has never started. Refusing to create
    Salons because a tuning table is missing would be an outage caused by a knob.

    The rollback matters as much as the answer: a failed statement leaves the session in a
    state where the very next query raises, and the caller is in the middle of creating a
    Salon."""

    class Broken:
        def execute(self, *args, **kwargs):
            raise RuntimeError("no such table: salon_settings")

        def __init__(self):
            self.rolled_back = False

        def rollback(self):
            self.rolled_back = True

    broken = Broken()

    assert ceiling(broken) == DEFAULT_CEILING
    assert broken.rolled_back is True


def test_the_ceiling_is_a_whole_number_of_people(db):
    """The settings table has one numeric column, so everything comes back as a float. Half
    a participant is not a thing to provision a room for."""
    _store(db, 5.0)

    assert ceiling(db) == 5
    assert isinstance(ceiling(db), int)


# ── What a host may ask for ───────────────────────────────────────────────────


def test_a_host_gets_the_size_they_asked_for():
    assert bounded(2, ceiling=3) == 2


def test_asking_for_more_than_the_ceiling_is_bounded_rather_than_refused():
    """They asked for the biggest Salon available, so they get the biggest available. A
    refusal would send somebody to a settings page to discover a number nobody published."""
    assert bounded(50, ceiling=3) == 3


def test_a_host_who_says_nothing_gets_the_ceiling():
    """Nothing chosen is not a Salon for nobody. The ceiling is the offer."""
    assert bounded(None, ceiling=3) == 3


def test_a_salon_for_one_is_not_a_conversation():
    """Two is the floor whatever was typed: one participant and their interpreter is
    somebody talking to a translation of themselves."""
    assert MINIMUM_CAP == 2
    assert bounded(1, ceiling=3) == 2
    assert bounded(0, ceiling=3) == 2
    assert bounded(-4, ceiling=3) == 2


def test_a_ceiling_below_the_floor_written_by_hand_is_still_survivable():
    """Only reachable through a row written by hand, since the settings refuse it. Returning
    1 anyway would turn one bad number into a 500 on every attempt to open a Salon, because
    the `salons` CHECK cannot store it."""
    assert bounded(None, ceiling=1) == MINIMUM_CAP
    assert bounded(3, ceiling=1) == MINIMUM_CAP


# ── A full Salon ──────────────────────────────────────────────────────────────


def test_a_salon_below_its_cap_takes_one_more():
    assert is_full(2, cap=3) is False


def test_a_salon_at_its_cap_is_full():
    assert is_full(3, cap=3) is True


def test_a_salon_over_its_cap_is_still_full():
    """A cap lowered under a Salon already above it. Reading `==` would let everybody in."""
    assert is_full(5, cap=3) is True


def test_the_refusal_says_how_many_fit():
    """Clear enough to act on. "The room is full" leaves somebody wondering whether to wait,
    and the number is what tells them this is not a moment's queue."""
    message = room_full_message(cap=3)

    assert "3" in message
    assert message.endswith(".")


# ── At the door ───────────────────────────────────────────────────────────────


@pytest.fixture
def host(db):
    from src.models.user import User
    from src.services.jwt_service import issue_token

    user = User(email="caphost@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, issue_token(str(user.id))


def _salon(db, host_user, *, cap):
    from src.models.salon import Salon

    row = Salon(
        host_user_id=host_user.id,
        livekit_room_name=f"salon-cap-{cap}-{host_user.id.hex[:6]}",
        source_type="url",
        source_content="c",
        status="active",
        participant_cap=cap,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _invite(db, salon, host_user, *, token, status="pending"):
    from datetime import datetime, timedelta, timezone

    from src.models.invitation import Invitation

    row = Invitation(
        salon_id=salon.id,
        host_user_id=host_user.id,
        guest_email=f"{token}@example.com",
        guest_phone="",
        invitation_type="email_contact",
        join_token=token,
        status=status,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(row)
    db.commit()
    return row


def test_a_guest_gets_in_while_there_is_room(client, db, host):
    host_user, _ = host
    salon = _salon(db, host_user, cap=3)
    _invite(db, salon, host_user, token="cap-free")

    assert client.get("/invitations/guest-join/cap-free").status_code == 200


def test_the_last_seat_is_still_a_seat(client, db, host):
    """Two taken of three — the host and one accepted guest — leaves exactly one."""
    host_user, _ = host
    salon = _salon(db, host_user, cap=3)
    _invite(db, salon, host_user, token="cap-first", status="accepted")
    _invite(db, salon, host_user, token="cap-second")

    assert client.get("/invitations/guest-join/cap-second").status_code == 200


def test_a_full_salon_refuses_the_next_person(client, db, host):
    host_user, _ = host
    salon = _salon(db, host_user, cap=3)
    _invite(db, salon, host_user, token="cap-a", status="accepted")
    _invite(db, salon, host_user, token="cap-b", status="accepted")
    _invite(db, salon, host_user, token="cap-c")

    resp = client.get("/invitations/guest-join/cap-c")

    assert resp.status_code == 409


def test_the_refusal_is_readable_rather_than_a_dead_link(client, db, host):
    """LiveKit's own limit rejects the connection silently, and a guest whose link simply
    does not work cannot tell a full Salon from a broken one."""
    host_user, _ = host
    salon = _salon(db, host_user, cap=2)
    _invite(db, salon, host_user, token="cap-word", status="accepted")
    _invite(db, salon, host_user, token="cap-word-2")

    detail = client.get("/invitations/guest-join/cap-word-2").json()["detail"]

    assert "full" in detail.lower()
    assert "2" in detail


def test_somebody_already_admitted_is_not_turned_away_by_a_full_room(client, db, host):
    """Their seat is one of the ones counted. Re-fetching credentials — a reload, a second
    device — must not read as a fourth person arriving."""
    host_user, _ = host
    salon = _salon(db, host_user, cap=2)
    _invite(db, salon, host_user, token="cap-inside", status="accepted")

    assert client.get("/invitations/guest-join/cap-inside").status_code == 410


def test_a_ceiling_lowered_afterwards_does_not_shrink_an_open_salon(client, db, host):
    """The Salon keeps the size its host was promised. A ceiling is what is allowed now; the
    cap on the row is what was offered then, and lowering one must not empty the other."""
    host_user, _ = host
    salon = _salon(db, host_user, cap=3)
    _store(db, 2)
    db.commit()
    _invite(db, salon, host_user, token="cap-promised", status="accepted")
    _invite(db, salon, host_user, token="cap-promised-2")

    assert client.get("/invitations/guest-join/cap-promised-2").status_code == 200
