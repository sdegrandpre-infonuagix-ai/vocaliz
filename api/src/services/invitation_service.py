"""Voice invitation service — resolves phone to Salon user or SMS contact."""
import secrets
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException
from sqlalchemy.orm import Session, aliased

from src.config import settings
from src.models.invitation import Invitation
from src.models.session import SessionModel
from src.models.user import User


def invite_guest(session_id: str, host_user: User, guest_phone: str, db: Session) -> dict:
    """
    Invite guest_phone to session_id.
    Raises ValueError for session not found; HTTPException(503) if SMS fails.
    """
    import uuid as _uuid

    session_id_uuid = _uuid.UUID(str(session_id))

    # Verify session belongs to this host
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id_uuid,
        SessionModel.host_user_id == host_user.id,
    ).first()
    if not session:
        raise ValueError("session_not_found")

    # Idempotency: return existing pending invitation if sent <5 min ago
    cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    recent = (
        db.query(Invitation)
        .filter(
            Invitation.session_id == session_id_uuid,
            Invitation.guest_phone == guest_phone,
            Invitation.status == "pending",
        )
        .order_by(Invitation.created_at.desc())
        .first()
    )
    if recent is not None:
        created = recent.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created > cutoff:
            return _build_response(recent, session)

    # Determine type: registered Salon user or phone-only contact
    guest_user = db.query(User).filter(User.phone_number == guest_phone).first()
    invitation_type = "salon_friend" if guest_user else "sms_contact"

    join_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=24)

    invitation = Invitation(
        session_id=session_id_uuid,
        host_user_id=host_user.id,
        guest_phone=guest_phone,
        guest_user_id=guest_user.id if guest_user else None,
        invitation_type=invitation_type,
        join_token=join_token,
        status="pending",
        expires_at=expires_at,
    )
    db.add(invitation)
    db.flush()  # assigns PK without committing; rolled back if SMS fails

    if invitation_type == "sms_contact":
        join_link = f"{settings.salon_web_base_url}/join/{join_token}"
        try:
            _send_invitation_sms(guest_phone, join_link)
        except HTTPException:
            db.rollback()
            raise

    db.commit()
    db.refresh(invitation)
    return _build_response(invitation, session)


def _build_response(invitation: Invitation, session: SessionModel) -> dict:
    join_link = None
    if invitation.invitation_type == "sms_contact":
        join_link = f"{settings.salon_web_base_url}/join/{invitation.join_token}"
    return {
        "invitationId": str(invitation.id),
        "invitationType": invitation.invitation_type,
        "guestPhone": invitation.guest_phone,
        "status": invitation.status,
        "joinLink": join_link,
    }


def get_pending_invitations_for_user(user: User, db: Session) -> list[dict]:
    """Return pending in-app invitations addressed to this user (salon_friend type)."""
    now = datetime.now(tz=timezone.utc)
    HostUser = aliased(User)
    rows = (
        db.query(Invitation, SessionModel, HostUser)
        .join(SessionModel, Invitation.session_id == SessionModel.id)
        .join(HostUser, SessionModel.host_user_id == HostUser.id)
        .filter(
            Invitation.guest_user_id == user.id,
            Invitation.invitation_type == "salon_friend",
            Invitation.status == "pending",
            Invitation.expires_at > now,
        )
        .all()
    )

    result = []
    for inv, sess, host in rows:
        expires = inv.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        created = inv.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        result.append({
            "invitationId": str(inv.id),
            "sessionId": str(sess.id),
            "livekitRoomName": sess.livekit_room_name,
            "hostPhone": host.phone_number,
            "joinToken": inv.join_token,
            "createdAt": created.isoformat(),
            "expiresAt": expires.isoformat(),
        })
    return result


def _send_invitation_sms(phone_number: str, join_link: str) -> None:
    client = boto3.client("sns", region_name=settings.aws_region)
    message = f"Vous avez été invité à rejoindre une conversation Salon. Rejoignez ici : {join_link}"
    try:
        client.publish(
            PhoneNumber=phone_number,
            Message=message,
            MessageAttributes={
                "AWS.SNS.SMS.SenderID": {"DataType": "String", "StringValue": settings.sns_sender_id},
                "AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"},
            },
        )
    except ClientError as exc:
        raise HTTPException(
            status_code=503, detail="Service d'envoi SMS indisponible."
        ) from exc
