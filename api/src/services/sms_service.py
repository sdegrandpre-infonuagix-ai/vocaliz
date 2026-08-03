"""Sending the join link by text message.

A second channel, not a replacement: a guest reached by text is opening the link on the
phone they are holding, which is where the microphone actually works. Email remains the
channel that carries the invitation when there is an address.

Bilingual like every other message Vocaliz sends, and for the same reason — the
recipient's language is not knowable at send time. Short, because a text message that
runs to three parts arrives out of order on some carriers and reads as gibberish.
"""
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.config import settings

logger = logging.getLogger(__name__)

_client = None


def _sns():
    """Built once and reused: a boto3 client costs about a second to construct."""
    global _client
    if _client is None:
        _client = boto3.client("sns", region_name=settings.aws_region)
    return _client


def invitation_text(join_link: str, phone_pin: str = "") -> str:
    """The message body, both languages, under the two-part limit.

    The link comes first. Everything after it is advice, and advice that pushes the one
    actionable thing below the fold is worse than no advice.
    """
    # Included only when there is both a code and a number to call. A code with nowhere
    # to dial it is noise in a message that has to stay under two parts.
    telephone = ""
    if phone_pin and settings.salon_phone_number:
        telephone = f"Or call {settings.salon_phone_number} and enter {phone_pin}. "

    return (
        f"Vocaliz: you are invited to a conversation. {join_link} "
        f"{telephone}"
        "Open it in Safari or Chrome, not inside a messaging app. "
        "Valid once, for 24 hours. "
        "What is said is transcribed and kept so it can be translated.\n"
        f"Vocaliz : vous etes invite a une conversation. {join_link} "
        "Ouvrez-le dans Safari ou Chrome, pas dans une application de messagerie. "
        "Valable une fois, 24 heures. "
        "Ce qui se dit est transcrit et conserve afin de pouvoir etre traduit."
    )


def send_invitation_sms(phone: str, join_link: str, phone_pin: str = "") -> bool:
    """Text the join link. Reports delivery rather than raising.

    Best-effort like the email path: the invitation is already committed and the link
    works over any channel, so a carrier refusing the message must not cost the host the
    thing they were trying to share.
    """
    if not phone:
        return False
    try:
        _sns().publish(
            PhoneNumber=phone,
            Message=invitation_text(join_link, phone_pin),
            MessageAttributes={
                # Transactional, not promotional: an invitation to a conversation starting
                # now must not be held back or dropped by carrier promotional filtering.
                "AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"},
                # No SenderID. Alphabetic sender IDs are not supported in Canada or the
                # United States, which is where these messages go: carriers there require
                # a real origination number and ignore — or reject — anything else. What
                # the recipient sees is the number the account sends from, not a name.
            },
        )
        return True
    except (BotoCoreError, ClientError):
        logger.warning("Invitation SMS to %s failed", phone[-4:], exc_info=True)
        return False
