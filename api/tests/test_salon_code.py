"""The telephone code pool: claiming, releasing, and resolving a dialled code."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.invitation import Invitation
from src.models.salon_code import CODE_DIGITS, CodeAvailable
from src.models.session import SessionModel
from src.models.user import User
from src.services import salon_code_service


@pytest.fixture
def salon(db):
    user = User(email="codehost@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    s = SessionModel(
        host_user_id=user.id,
        livekit_room_name="salon-codes",
        source_type="url",
        source_content="c",
        status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _invitation(db, salon, code, *, email="guest@example.com", status="pending"):
    row = Invitation(
        session_id=salon.id,
        host_user_id=salon.host_user_id,
        guest_email=email,
        guest_phone="",
        invitation_type="email_contact",
        join_token=f"tok-{code}",
        phone_pin=code,
        status=status,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ─── Claiming ─────────────────────────────────────────────────────────────────

def test_a_claim_yields_six_digits(db):
    code = salon_code_service.claim(db)
    assert code is not None and len(code) == CODE_DIGITS and code.isdigit()


def test_a_claimed_code_is_reserved_and_stamped(db):
    code = salon_code_service.claim(db)
    row = db.get(CodeAvailable, code)
    assert row.available is False
    assert row.claimed_at is not None


def test_the_pool_grows_only_with_use(db):
    """Pre-generating a million rows to hand out a handful would be storage spent on
    nothing."""
    salon_code_service.claim(db)
    salon_code_service.claim(db)
    assert db.query(CodeAvailable).count() == 2


def test_two_claims_never_return_the_same_code(db):
    """One code per invitation. A shared code would leave the caller anonymous, and
    salon_events requires an identity."""
    assert salon_code_service.claim(db) != salon_code_service.claim(db)


def test_a_free_code_is_reused_before_a_new_one_is_minted(db):
    """Keeps the table bounded by concurrent use rather than by total use."""
    code = salon_code_service.claim(db)
    assert salon_code_service.release(db, [code]) == 1
    assert salon_code_service.claim(db) == code
    assert db.query(CodeAvailable).count() == 1


# ─── Releasing ────────────────────────────────────────────────────────────────

def test_releasing_clears_the_reservation(db):
    code = salon_code_service.claim(db)
    salon_code_service.release(db, [code])
    row = db.get(CodeAvailable, code)
    assert row.available is True
    assert row.claimed_at is None


def test_releasing_a_free_code_changes_nothing(db):
    code = salon_code_service.claim(db)
    salon_code_service.release(db, [code])
    assert salon_code_service.release(db, [code]) == 0


def test_a_session_releases_the_codes_of_its_invitations(db, salon):
    """Found through the invitations rather than stored against the session, because that
    is where the mapping already lives."""
    first, second = salon_code_service.claim(db), salon_code_service.claim(db)
    _invitation(db, salon, first, email="a@example.com")
    _invitation(db, salon, second, email="b@example.com")

    assert salon_code_service.release_for_session(db, salon.id) == 2
    assert db.query(CodeAvailable).filter(CodeAvailable.available.is_(False)).count() == 0


def test_a_session_with_no_codes_releases_nothing(db, salon):
    assert salon_code_service.release_for_session(db, salon.id) == 0


# ─── Resolving a dialled code ─────────────────────────────────────────────────

def test_a_dialled_code_identifies_the_guest_not_just_the_room(db, salon):
    """The whole reason the code is per invitation: the caller has to be recordable."""
    code = salon_code_service.claim(db)
    _invitation(db, salon, code, email="caller@example.com")
    found = salon_code_service.invitation_for_code(db, code)
    assert found is not None
    assert found.guest_email == "caller@example.com"
    assert found.session_id == salon.id


def test_a_released_code_resolves_to_nothing(db, salon):
    """Otherwise a caller dialling an old code lands in a conversation that is over."""
    code = salon_code_service.claim(db)
    _invitation(db, salon, code)
    salon_code_service.release(db, [code])
    assert salon_code_service.invitation_for_code(db, code) is None


def test_an_accepted_invitation_no_longer_answers(db, salon):
    """The link is one-time and so is the code."""
    code = salon_code_service.claim(db)
    _invitation(db, salon, code, status="accepted")
    assert salon_code_service.invitation_for_code(db, code) is None


def test_an_unknown_code_resolves_to_nothing(db):
    assert salon_code_service.invitation_for_code(db, "000000") is None


def test_a_malformed_code_is_rejected_before_any_lookup(db):
    for value in ("", "12345", "1234567", None):
        assert salon_code_service.invitation_for_code(db, value) is None


# ─── What the schema forbids ──────────────────────────────────────────────────

def test_a_reserved_code_must_carry_a_claim_time(db):
    """Without it nothing can tell a leaked reservation from one in honest use."""
    db.add(CodeAvailable(code="111111", available=False, claimed_at=None))
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_free_code_must_not_carry_one(db):
    db.add(
        CodeAvailable(
            code="222222", available=True, claimed_at=datetime.now(tz=timezone.utc)
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_code_of_the_wrong_length_is_refused(db):
    """A keypad cannot enter anything else, so a code that is not six digits is one nobody
    can ever reach."""
    db.add(CodeAvailable(code="123", available=True))
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_code_with_a_letter_is_refused(db):
    """Six digits, not six characters. A keypad cannot enter a letter, so this would be a
    code nobody could ever dial — stored, reserved and unreachable."""
    db.add(CodeAvailable(code="12a456", available=True))
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_code_with_a_space_is_refused(db):
    db.add(CodeAvailable(code="12 456", available=True))
    with pytest.raises(IntegrityError):
        db.commit()


def test_every_digit_is_accepted(db):
    """Guards the replace chain: a bug in it could reject a legitimate digit rather than
    only letters, and the failure would look like a saturated pool."""
    db.add(CodeAvailable(code="012345", available=True))
    db.add(CodeAvailable(code="678900", available=True))
    db.commit()
    assert db.query(CodeAvailable).count() == 2


# ─── The code a pending invitation still holds ────────────────────────────────
#
# The outage this section exists for: ending a salon returned its telephone codes to the pool
# without closing the invitations that carried them. A pending invitation holds its code under
# a partial unique index, so the pool was offering a code that was still spoken for.
#
# It did not fail one invitation. The pool hands out its oldest free code first, so the same
# poisoned value came back on every claim and every invitation in the system answered 500 —
# for hosts with no connection to the salon that left the row behind.

def test_a_code_still_held_by_a_pending_invitation_is_not_handed_out(db, salon):
    """The claim itself. Free in the pool and owned by a pending row is the exact state that
    produced the IntegrityError, and a claim must see the second half."""
    _invitation(db, salon, "111111", status="pending")
    db.add(CodeAvailable(code="111111", available=True))
    db.commit()

    assert salon_code_service.claim(db) != "111111"


def test_the_stale_code_does_not_merely_move_down_the_queue(db, salon):
    """It is the *oldest* free code that gets handed out, which is what made one bad row a
    permanent outage rather than a single failure. Claiming repeatedly must never reach it."""
    _invitation(db, salon, "222222", status="pending")
    db.add(CodeAvailable(code="222222", available=True))
    db.commit()

    assert all(salon_code_service.claim(db) != "222222" for _ in range(5))


def test_a_code_held_by_a_closed_invitation_is_reusable(db, salon):
    """The guard must not overreach. An accepted or expired invitation holds nothing — the
    index says so — and refusing its code would drain the pool one salon at a time."""
    _invitation(db, salon, "333333", status="expired")
    db.add(CodeAvailable(code="333333", available=True))
    db.commit()

    assert salon_code_service.claim(db) == "333333"


def test_two_pending_invitations_cannot_share_a_code(db, salon):
    """The index itself, which was invisible to every test until it was declared on the model.
    Without this the service guard above could be removed and nothing would notice.

    The second row is built by hand rather than through the helper: that one derives the join
    token from the code, so a shared code would collide on the token first and this test would
    pass without the index existing at all."""
    _invitation(db, salon, "444444", status="pending")
    db.add(
        Invitation(
            session_id=salon.id,
            host_user_id=salon.host_user_id,
            guest_email="other@example.com",
            guest_phone="",
            invitation_type="email_contact",
            join_token="a-different-token",
            phone_pin="444444",
            status="pending",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_closed_invitation_does_not_reserve_its_code_forever(db, salon):
    """The index is partial, and that is the half a plain unique index would get wrong. A code
    is reusable once its invitation is closed; forbidding that would retire six digits per
    guest ever invited."""
    _invitation(db, salon, "555555", status="accepted")
    db.add(
        Invitation(
            session_id=salon.id,
            host_user_id=salon.host_user_id,
            guest_email="later@example.com",
            guest_phone="",
            invitation_type="email_contact",
            join_token="a-later-token",
            phone_pin="555555",
            status="pending",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
        )
    )
    db.commit()   # must not raise
    assert db.query(Invitation).filter(Invitation.phone_pin == "555555").count() == 2
