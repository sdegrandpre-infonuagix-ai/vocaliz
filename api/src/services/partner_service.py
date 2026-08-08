"""Previous-partner discovery — powers quick-start with a known partner (Story 5.2)."""
from sqlalchemy.orm import Session as DbSession

from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.user import User


def _iso(dt):
    from datetime import timezone

    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def get_previous_partners(user: User, db: DbSession) -> list[dict]:
    """Return the distinct discussion partners this user has shared a salon with.

    A partner is anyone the user has hosted (their invited guests) or been hosted by
    (the host of salons they joined as an accepted guest). Deduplicated by the
    partner's account when known, otherwise by email. Most recently seen first.

    Enables Story 5.2: the app shows this list so a user can start a new salon with
    a known partner without repeating the full voice-invitation flow.
    """
    # Aggregate by a stable key: the partner's user id when registered, else email.
    partners: dict[str, dict] = {}

    def _record(*, user_id, email, seen_at):
        key = f"u:{user_id}" if user_id else f"e:{email}"
        entry = partners.get(key)
        if entry is None:
            partners[key] = {
                "userId": str(user_id) if user_id else None,
                "email": email,
                "lastSalonAt": seen_at,
                "salonCount": 1,
            }
            return
        entry["salonCount"] += 1
        # Keep the most recent timestamp.
        if seen_at and (entry["lastSalonAt"] is None or seen_at > entry["lastSalonAt"]):
            entry["lastSalonAt"] = seen_at

    # 1. Salons this user hosted → partners are the invited guests.
    host_salons = (
        db.query(Salon).filter(Salon.host_user_id == user.id).all()
    )
    host_salon_map = {s.id: s for s in host_salons}
    if host_salon_map:
        invitations = (
            db.query(Invitation)
            .filter(Invitation.salon_id.in_(host_salon_map.keys()))
            .all()
        )
        for inv in invitations:
            sess = host_salon_map.get(inv.salon_id)
            email = inv.guest_email
            partner_user_id = inv.guest_user_id
            if partner_user_id:
                guest_user = db.query(User).filter(User.id == partner_user_id).first()
                if guest_user:
                    email = guest_user.email
            _record(
                user_id=partner_user_id,
                email=email,
                seen_at=_iso(sess.created_at) if sess else None,
            )

    # 2. Salons this user joined as an accepted guest → partner is the host.
    guest_invitations = (
        db.query(Invitation)
        .filter(
            Invitation.guest_user_id == user.id,
            Invitation.status == "accepted",
        )
        .all()
    )
    guest_salon_ids = {
        inv.salon_id for inv in guest_invitations
    } - set(host_salon_map.keys())
    if guest_salon_ids:
        guest_salons = (
            db.query(Salon).filter(Salon.id.in_(guest_salon_ids)).all()
        )
        for sess in guest_salons:
            host_user = db.query(User).filter(User.id == sess.host_user_id).first()
            if host_user:
                _record(
                    user_id=host_user.id,
                    email=host_user.email,
                    seen_at=_iso(sess.created_at),
                )

    ordered = sorted(
        partners.values(),
        key=lambda p: p["lastSalonAt"] or "",
        reverse=True,
    )
    return ordered
