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
