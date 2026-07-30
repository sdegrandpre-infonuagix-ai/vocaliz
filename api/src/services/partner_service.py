"""Previous-partner discovery — powers quick-start with a known partner (Story 5.2)."""
from sqlalchemy.orm import Session

from src.models.invitation import Invitation
from src.models.session import SessionModel
from src.models.user import User


def _iso(dt):
    from datetime import timezone

    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def get_previous_partners(user: User, db: Session) -> list[dict]:
    """Return the distinct discussion partners this user has shared a session with.

    A partner is anyone the user has hosted (their invited guests) or been hosted by
    (the host of sessions they joined as an accepted guest). Deduplicated by the
    partner's account when known, otherwise by phone number. Most recently seen first.

    Enables Story 5.2: the app shows this list so a user can start a new session with
    a known partner without repeating the full voice-invitation flow.
    """
    # Aggregate by a stable key: the partner's user id when registered, else phone.
    partners: dict[str, dict] = {}

    def _record(*, user_id, phone, seen_at):
        key = f"u:{user_id}" if user_id else f"p:{phone}"
        entry = partners.get(key)
        if entry is None:
            partners[key] = {
                "userId": str(user_id) if user_id else None,
                "phoneNumber": phone,
                "lastSessionAt": seen_at,
                "sessionCount": 1,
            }
            return
        entry["sessionCount"] += 1
        # Keep the most recent timestamp.
        if seen_at and (entry["lastSessionAt"] is None or seen_at > entry["lastSessionAt"]):
            entry["lastSessionAt"] = seen_at

    # 1. Sessions this user hosted → partners are the invited guests.
    host_sessions = (
        db.query(SessionModel).filter(SessionModel.host_user_id == user.id).all()
    )
    host_session_map = {s.id: s for s in host_sessions}
    if host_session_map:
        invitations = (
            db.query(Invitation)
            .filter(Invitation.session_id.in_(host_session_map.keys()))
            .all()
        )
        for inv in invitations:
            sess = host_session_map.get(inv.session_id)
            phone = inv.guest_phone
            partner_user_id = inv.guest_user_id
            if partner_user_id:
                guest_user = db.query(User).filter(User.id == partner_user_id).first()
                if guest_user:
                    phone = guest_user.phone_number
            _record(
                user_id=partner_user_id,
                phone=phone,
                seen_at=_iso(sess.created_at) if sess else None,
            )

    # 2. Sessions this user joined as an accepted guest → partner is the host.
    guest_invitations = (
        db.query(Invitation)
        .filter(
            Invitation.guest_user_id == user.id,
            Invitation.status == "accepted",
        )
        .all()
    )
    guest_session_ids = {
        inv.session_id for inv in guest_invitations
    } - set(host_session_map.keys())
    if guest_session_ids:
        guest_sessions = (
            db.query(SessionModel).filter(SessionModel.id.in_(guest_session_ids)).all()
        )
        for sess in guest_sessions:
            host_user = db.query(User).filter(User.id == sess.host_user_id).first()
            if host_user:
                _record(
                    user_id=host_user.id,
                    phone=host_user.phone_number,
                    seen_at=_iso(sess.created_at),
                )

    ordered = sorted(
        partners.values(),
        key=lambda p: p["lastSessionAt"] or "",
        reverse=True,
    )
    return ordered
