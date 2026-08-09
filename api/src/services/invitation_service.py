"""Voice invitation service — resolves an email to a Vocaliz user or an email contact."""
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException
from sqlalchemy.orm import Session as DbSession, aliased

from src.config import settings
from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.user import User
from src.services import livekit_service, salon_code_service, sms_service
from src.services.email_text import bilingual_body, bilingual_subject
from src.signup import identifiers_of, normalise_email, normalise_phone, register

logger = logging.getLogger(__name__)


def invite_guest(
    salon_id: str,
    host_user: User,
    db: DbSession,
    guest_email: str | None = None,
    guest_phone: str | None = None,
) -> dict:
    """Invite someone to a salon by email, by text message, or by both.

    One of the two is required and neither is privileged: a host may hold an address, a
    number, or both, and the join link is the same whichever way it travels. Absent is
    stored as an empty string rather than NULL, matching salon_events, so the two tables
    answer "do we have an address" the same way.

    Raises ValueError("contact_required") when both are missing, and
    ValueError("salon_not_found") when the salon is not this host's. Delivery is
    reported in the response, never raised: the invitation is committed first and the
    link works over any channel, so a failed send still leaves the host something to
    share by hand.
    """
    import uuid as _uuid

    guest_email = (guest_email or "").strip().lower()
    guest_phone = (guest_phone or "").strip()
    if not guest_email and not guest_phone:
        raise ValueError("contact_required")

    salon_id_uuid = _uuid.UUID(str(salon_id))

    # Verify salon belongs to this host
    salon = db.query(Salon).filter(
        Salon.id == salon_id_uuid,
        Salon.host_user_id == host_user.id,
    ).first()
    if not salon:
        raise ValueError("salon_not_found")

    # Idempotency: return existing pending invitation if sent <5 min ago
    cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    # Matched on whichever contact the host gave. An empty string would match every
    # phone-only invitation ever sent to this salon, and hand back the wrong link.
    same_contact = (
        (Invitation.guest_email == guest_email)
        if guest_email
        else (Invitation.guest_phone == guest_phone)
    )
    recent = (
        db.query(Invitation)
        .filter(
            Invitation.salon_id == salon_id_uuid,
            same_contact,
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
            return _build_response(recent, salon, sent=_try_send(recent))

    # Determine type: registered Vocaliz user or an email-only contact. Looked up by
    # address only — a phone number is not an account handle here, sign-in having moved
    # to email.
    guest_user = (
        db.query(User).filter(User.email == guest_email).first() if guest_email else None
    )
    invitation_type = "salon_friend" if guest_user else "email_contact"

    join_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=24)

    invitation = Invitation(
        salon_id=salon_id_uuid,
        host_user_id=host_user.id,
        guest_email=guest_email,
        guest_phone=guest_phone,
        guest_user_id=guest_user.id if guest_user else None,
        invitation_type=invitation_type,
        join_token=join_token,
        # Claimed from the pool, not minted here. One code per invitation, so a caller is
        # identified by the invitation rather than merely placed in the right room.
        phone_pin=salon_code_service.claim(db),
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
    return _build_response(invitation, salon, sent=_try_send(invitation))


def _try_send(invitation: Invitation) -> tuple[bool, bool]:
    """Send the join link over every channel the host supplied.

    Returns (email_sent, sms_sent). A channel that was not asked for reports False, which
    the response distinguishes from a channel that failed by also returning what was
    requested — otherwise "not sent" and "not attempted" would look identical to the host.

    Neither failure is fatal: the invitation is already committed and the link works over
    any channel, so the host keeps something to share by hand.
    """
    link = _join_link(invitation.join_token)

    email_sent = False
    if invitation.guest_email:
        try:
            _send_invitation_email(invitation.guest_email, link, invitation.phone_pin or "")
            email_sent = True
        except HTTPException as exc:
            logger.warning("Invitation %s: email failed: %s", invitation.id, exc.detail)

    sms_sent = False
    if invitation.guest_phone:
        sms_sent = sms_service.send_invitation_sms(
            invitation.guest_phone, link, invitation.phone_pin or ""
        )

    return email_sent, sms_sent


def _join_link(join_token: str) -> str:
    return f"{settings.salon_web_base_url}/join/{join_token}"


def _build_response(
    invitation: Invitation,
    salon: Salon,
    *,
    sent: tuple[bool, bool] = (False, False),
) -> dict:
    # The link is returned for every invitation type, including salon_friend. A join token
    # is minted for all of them and guest_join_salon validates it without looking at the
    # type, so withholding it from registered friends served no purpose — it just left the
    # host with nothing to share when the in-app notification was not a practical channel.
    return {
        "invitationId": str(invitation.id),
        "invitationType": invitation.invitation_type,
        "guestEmail": invitation.guest_email,
        "guestPhone": invitation.guest_phone,
        "status": invitation.status,
        "joinLink": _join_link(invitation.join_token),
        # Handed back so the host can read it out to a guest who never got the message.
        "phonePin": invitation.phone_pin or "",
        # Each channel reports separately, and only for a channel that was asked for.
        # Collapsing them into one flag would tell a host who gave both that "it was
        # sent" when only one of the two actually left.
        "emailSent": sent[0],
        "smsSent": sent[1],
        # Handed back at creation time, so the host holds the guest's future room identity
        # before the guest has opened the link.
        "participantIdentity": livekit_service.identity_for(invitation),
        # And the label that identity will wear in the room, so the host can tell which
        # "Guest XXXX" is the person they invited — the mapping to an email exists only
        # here, for the host, and is never published to the other participants.
        "participantName": livekit_service.guest_display_name(invitation.id),
    }


def send_invitation_email(invitation_id: str, host_user: User, db: DbSession) -> dict:
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


def get_pending_invitations_for_user(user: User, db: DbSession) -> list[dict]:
    """Return pending in-app invitations addressed to this user (salon_friend type)."""
    now = datetime.now(tz=timezone.utc)
    HostUser = aliased(User)
    rows = (
        db.query(Invitation, Salon, HostUser)
        .join(Salon, Invitation.salon_id == Salon.id)
        .join(HostUser, Salon.host_user_id == HostUser.id)
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
            "salonId": str(sess.id),
            "livekitRoomName": sess.livekit_room_name,
            "hostEmail": host.email,
            "hostPhone": host.phone_number,
            "joinToken": inv.join_token,
            "createdAt": created.isoformat(),
            "expiresAt": expires.isoformat(),
        })
    return result


def link_prior_invitations(user: User, db: DbSession) -> int:
    """Link this user's earlier invitations to their newly registered account.

    Called after OTP verification. Updates guest_user_id on all prior email_contact
    invitations so the app can recognise their participation (Story 3.5).
    Returns the count of invitations linked.

    Correlating on email is what makes this reliable: an account always has one, whereas
    the phone number this used to match on became optional when sign-in moved to email,
    leaving earlier participation impossible to reattach.
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


def send_followup_email_to_guests(salon_id_str: str, db: DbSession) -> int:
    """Email an app-install link to guests without an account who completed this salon (FR30).

    Called after a salon is marked ended. Returns the count of emails sent.
    Errors on individual sends are swallowed so salon end is never blocked.
    Only targets invitations of type 'email_contact' that were actually accepted.
    """
    import uuid as _uuid

    try:
        salon_uuid = _uuid.UUID(str(salon_id_str))
    except ValueError:
        return 0

    accepted_guest_invitations = (
        db.query(Invitation)
        .filter(
            Invitation.salon_id == salon_uuid,
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
                # The host console, not the app store. Someone who has just taken part
                # already knows what a Salon is; the next step worth offering is holding
                # their own, and the console does that in a browser with nothing to
                # install. An install link asks for a commitment before the value is
                # obvious, and drops anyone reading this on a desktop.
                bilingual_body(
                    "Thank you for taking part in a Salon conversation!\n\n"
                    "Want to host one of your own? Start here, in your browser — nothing "
                    "to install:\n"
                    f"{settings.salon_web_base_url}/host",
                    "Merci d'avoir participé à une conversation Salon !\n\n"
                    "Envie d'en animer une vous-même ? Commencez ici, dans votre "
                    "navigateur — rien à installer :\n"
                    f"{settings.salon_web_base_url}/host",
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


def _send_invitation_email(to_address: str, join_link: str, phone_pin: str = "") -> None:
    # Included only when there is a code and a number to dial. Promising a telephone
    # option before the platform has a number would be worse than not mentioning it.
    telephone_line_en = ""
    telephone_line_fr = ""
    if phone_pin and settings.salon_phone_number:
        telephone_line_en = (
            f"Prefer to join by phone? Call {settings.salon_phone_number} and enter "
            f"{phone_pin} when asked.\n\n"
        )
        telephone_line_fr = (
            f"Vous préférez rejoindre par téléphone ? Composez "
            f"{settings.salon_phone_number} et entrez le {phone_pin} lorsqu'on vous le "
            f"demande.\n\n"
        )

    # The link is repeated in both halves rather than shared between them. It is the one
    # thing the recipient has to act on, and it must be within reach of whichever half
    # they actually read.
    _send_email(
        to_address,
        bilingual_subject(
            "You are invited to a Salon conversation",
            "Vous êtes invité à une conversation Salon",
        ),
        # The browser instruction is spelled out, and says why. "Open it in your browser"
        # was already there and was not enough: tapping a link inside a mail or messaging
        # app opens an embedded webview, and those routinely cannot reach the microphone —
        # sometimes without even showing a prompt. The guest then hears everyone and is
        # heard by no one, which reads as a broken product rather than a wrong browser.
        # Worse, the link is single-use, so reopening it properly needs a fresh invitation.
        bilingual_body(
            "You have been invited to join a Salon conversation.\n\n"
            f"Join here: {join_link}\n\n"
            "Open this link in Safari or Chrome, not inside your email app. Browsers built "
            "into email and messaging apps often cannot reach the microphone, and you would "
            "hear everyone while nobody hears you.\n\n"
            "This link works only once and expires in 24 hours.\n\n"
            f"{telephone_line_en}"
            # Placed last, after the link and the browser warning, but before they join:
            # this is the only moment a guest can decline by simply not coming. The agent
            # says it again in the room, for anyone who joined without reading this.
            "Please note: what is said in a Salon is transcribed and kept, so that each "
            "participant can read the conversation in the language they choose.",
            "Vous avez été invité à rejoindre une conversation Salon.\n\n"
            f"Rejoignez ici : {join_link}\n\n"
            "Ouvrez ce lien dans Safari ou Chrome, et non dans votre application de "
            "courriel. Les navigateurs intégrés aux applications de courriel et de "
            "messagerie n'accèdent souvent pas au microphone : vous entendriez tout le "
            "monde sans que personne ne vous entende.\n\n"
            "Ce lien ne fonctionne qu'une seule fois et expire dans 24 heures.\n\n"
            f"{telephone_line_fr}"
            "À noter : ce qui se dit dans un Salon est transcrit et conservé, afin que "
            "chaque participant puisse lire la conversation dans la langue de son choix.",
        ),
    )


def invite_caller(
    salon_id: str,
    host_user: User,
    db: DbSession,
    *,
    email: str | None = None,
    phone: str | None = None,
) -> dict:
    """A join link for somebody already in the room, carrying who they are.

    This is what the anonymous link became in Story 10.1. A link addressed to nobody left
    nothing to hold an allowance against: whoever had used their free minutes got them back by
    arriving again as a stranger, and no accounting downstream could tell. So an identifier is
    required here exactly as it is everywhere else, and `identifiers_of` refuses a call with
    neither.

    What survives from the anonymous version, because both reasons still hold. It is **not
    sent**: the person is already in the room and the link exists to give them an identity the
    room can name and the report can count. And it claims **no telephone PIN**: codes come from
    a finite pool of six digits and reach somebody only by text message, so reserving one for a
    caller who is already through would spend a scarce code on a channel nobody will use.

    Single-use needs no special handling. Every join token is spent once, at the moment the
    guest's microphone works, and a spent one answers 410 — see `guest_join_salon`.
    """
    identifiers_of(email=email, phone=phone)
    salon_uuid = uuid.UUID(str(salon_id))
    salon = db.query(Salon).filter(Salon.id == salon_uuid).first()
    if salon is None or salon.host_user_id != host_user.id:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")
    if salon.status != "active":
        raise HTTPException(status_code=409, detail="This salon is no longer active.")

    person = register(db, email=email, phone=phone)

    invitation = Invitation(
        salon_id=salon_uuid,
        host_user_id=host_user.id,
        # Empty rather than NULL for the channel that was not given: these are the same
        # columns the addressed invitations use, `invite_guest` normalises a missing number
        # to "" the same way, and the response schema types them as strings.
        guest_email=normalise_email(email),
        guest_phone=normalise_phone(phone),
        # The account the identifier resolves to. Which is what keys their quota: a caller
        # who rings twice is one person with one allowance, not two callers with one each.
        guest_user_id=person.id,
        invitation_type="telephone_caller",
        join_token=secrets.token_urlsafe(32),
        phone_pin=None,
        status="pending",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    logger.info(
        "Anonymous invitation %s created for salon %s", invitation.id, salon_id
    )
    # Nothing was sent, and both channels say so rather than reporting a success nobody asked
    # for: the host sharing it by hand is the delivery.
    return _build_response(invitation, salon, sent=(False, False))
