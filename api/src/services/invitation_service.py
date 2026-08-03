"""Voice invitation service — resolves an email to a Vocaliz user or an email contact."""
import logging
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
from src.services import livekit_service
from src.services.email_text import bilingual_body, bilingual_subject

logger = logging.getLogger(__name__)


def invite_guest(session_id: str, host_user: User, guest_email: str, db: Session) -> dict:
    """
    Invite guest_email to session_id.
    Raises ValueError for session not found; HTTPException(503) if the email fails.
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
            Invitation.guest_email == guest_email,
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
            # Idempotent on the token, not on the delivery: repeating the invitation
            # reuses the same one-time link but mails it again. A host who invites the
            # same address twice is telling us the first one did not arrive, and the
            # silent return was indistinguishable from a successful send.
            return _build_response(recent, session, email_sent=_try_send(recent))

    # Determine type: registered Vocaliz user or an email-only contact
    guest_user = db.query(User).filter(User.email == guest_email).first()
    invitation_type = "salon_friend" if guest_user else "email_contact"

    join_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=24)

    invitation = Invitation(
        session_id=session_id_uuid,
        host_user_id=host_user.id,
        guest_email=guest_email,
        guest_user_id=guest_user.id if guest_user else None,
        invitation_type=invitation_type,
        join_token=join_token,
        status="pending",
        expires_at=expires_at,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    # The invitation is committed before the email is attempted, deliberately. A failed
    # send used to roll it back, which destroyed the join link at the exact moment the
    # host most needed it to share by hand — and the link works whatever the channel
    # ("n'importe quel moyen"). Delivery is reported, never fatal.
    #
    # Sent for every invitation type, registered members included. The in-app notification
    # only reaches a member who opens the app; an invitation to a conversation happening
    # now has to arrive on its own. Email is the channel that always lands, so it is the
    # baseline and the notification is the extra — not the other way round.
    return _build_response(invitation, session, email_sent=_try_send(invitation))


def _try_send(invitation: Invitation) -> bool:
    """Mail the join link, reporting delivery instead of raising.

    A failed send must never be fatal here: the invitation is already committed and the
    link works over any channel, so the host keeps something to share by hand.
    """
    try:
        _send_invitation_email(invitation.guest_email, _join_link(invitation.join_token))
        return True
    except HTTPException as exc:
        logger.warning("Invitation %s: email failed: %s", invitation.id, exc.detail)
        return False


def _join_link(join_token: str) -> str:
    return f"{settings.salon_web_base_url}/join/{join_token}"


def _build_response(
    invitation: Invitation, session: SessionModel, *, email_sent: bool = False
) -> dict:
    # The link is returned for every invitation type, including salon_friend. A join token
    # is minted for all of them and guest_join_session validates it without looking at the
    # type, so withholding it from registered friends served no purpose — it just left the
    # host with nothing to share when the in-app notification was not a practical channel.
    return {
        "invitationId": str(invitation.id),
        "invitationType": invitation.invitation_type,
        "guestEmail": invitation.guest_email,
        "status": invitation.status,
        "joinLink": _join_link(invitation.join_token),
        "emailSent": email_sent,
        # Handed back at creation time, so the host holds the guest's future room identity
        # before the guest has opened the link.
        "participantIdentity": livekit_service.guest_identity(invitation.id),
        # And the label that identity will wear in the room, so the host can tell which
        # "Guest XXXX" is the person they invited — the mapping to an email exists only
        # here, for the host, and is never published to the other participants.
        "participantName": livekit_service.guest_display_name(invitation.id),
    }


def send_invitation_email(invitation_id: str, host_user: User, db: Session) -> dict:
    """(Re)send the join link for an existing invitation.

    Separate from creation so the host can show the link first and mail it after — or
    retry when the first attempt failed, without minting a second one-time token.
    """
    import uuid as _uuid

    try:
        invitation_uuid = _uuid.UUID(str(invitation_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Invitation not found.")

    invitation = (
        db.query(Invitation)
        .filter(
            Invitation.id == invitation_uuid,
            Invitation.host_user_id == host_user.id,
        )
        .first()
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found or access denied.")
    # No type check: a registered member is emailed like anyone else, so resending to one
    # is a legitimate request. Refusing it used to leave the host unable to re-notify a
    # friend who had simply not opened the app.
    if invitation.status != "pending":
        raise HTTPException(status_code=409, detail="This invitation has already been used.")

    _send_invitation_email(invitation.guest_email, _join_link(invitation.join_token))
    return {"invitationId": str(invitation.id), "guestEmail": invitation.guest_email}


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
            "hostEmail": host.email,
            "hostPhone": host.phone_number,
            "joinToken": inv.join_token,
            "createdAt": created.isoformat(),
            "expiresAt": expires.isoformat(),
        })
    return result


def link_prior_invitations(user: User, db: Session) -> int:
    """Link this user's prior anonymous invitations to their newly registered account.

    Called after OTP verification. Updates guest_user_id on all prior email_contact
    invitations so the app can recognise their participation (Story 3.5).
    Returns the count of invitations linked.

    Correlating on email is what makes this reliable: an account always has one, whereas
    the phone number this used to match on became optional when sign-in moved to email,
    leaving anonymous participation impossible to reattach.
    """
    prior = (
        db.query(Invitation)
        .filter(
            Invitation.guest_email == user.email,
            Invitation.guest_user_id.is_(None),
        )
        .all()
    )
    for inv in prior:
        inv.guest_user_id = user.id
    if prior:
        db.commit()
    return len(prior)


def send_followup_email_to_guests(session_id_str: str, db: Session) -> int:
    """Email an app-install link to anonymous guests who completed this session (FR30).

    Called after a session is marked ended. Returns the count of emails sent.
    Errors on individual sends are swallowed so session end is never blocked.
    Only targets invitations of type 'email_contact' that were actually accepted.
    """
    import uuid as _uuid

    try:
        session_uuid = _uuid.UUID(str(session_id_str))
    except ValueError:
        return 0

    accepted_guest_invitations = (
        db.query(Invitation)
        .filter(
            Invitation.session_id == session_uuid,
            Invitation.invitation_type == "email_contact",
            Invitation.status == "accepted",
        )
        .all()
    )

    sent = 0
    for inv in accepted_guest_invitations:
        try:
            _send_email(
                inv.guest_email,
                bilingual_subject(
                    "Thanks for taking part in Vocaliz",
                    "Merci d'avoir participé à Vocaliz",
                ),
                bilingual_body(
                    "Thank you for taking part in a Salon conversation!\n\n"
                    "Install the app for the full experience:\n"
                    f"{settings.salon_install_url}",
                    "Merci d'avoir participé à une conversation Salon !\n\n"
                    "Installez l'application pour une expérience complète :\n"
                    f"{settings.salon_install_url}",
                ),
            )
            sent += 1
        except Exception:  # noqa: BLE001
            pass
    return sent


def _send_email(to_address: str, subject: str, body: str) -> None:
    """Low-level SES send. Raises HTTPException(503) on ClientError."""
    client = boto3.client("sesv2", region_name=settings.aws_region)
    try:
        client.send_email(
            FromEmailAddress=settings.ses_from_address,
            Destination={"ToAddresses": [to_address]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                }
            },
        )
    except ClientError as exc:
        logger.error("SES invitation send failed for %s: %s", to_address, exc, exc_info=True)
        raise HTTPException(
            status_code=503, detail="Email delivery service unavailable."
        ) from exc


def _send_invitation_email(to_address: str, join_link: str) -> None:
    # The link is repeated in both halves rather than shared between them. It is the one
    # thing the recipient has to act on, and it must be within reach of whichever half
    # they actually read.
    _send_email(
        to_address,
        bilingual_subject(
            "You are invited to a Salon conversation",
            "Vous êtes invité à une conversation Salon",
        ),
        bilingual_body(
            "You have been invited to join a Salon conversation.\n\n"
            f"Join here: {join_link}\n\n"
            "This link works only once and expires in 24 hours. "
            "Open it directly in your browser.",
            "Vous avez été invité à rejoindre une conversation Salon.\n\n"
            f"Rejoignez ici : {join_link}\n\n"
            "Ce lien ne fonctionne qu'une seule fois et expire dans 24 heures. "
            "Ouvrez-le directement dans votre navigateur.",
        ),
    )
