"""The hourly participant report, mailed to the administrator.

One table, one row per person, aggregated across every salon they took part in. Built here
rather than in the admin router so that the endpoint a human reads and the email a schedule
sends cannot drift into disagreeing about what a "participant" is.

Two of the eight columns are weaker than they look, and the report says so rather than letting
a reader assume otherwise:

  Pays      the browser's locale region, self-reported. Nothing collects a position and no
            viewer-country header reaches this application, so this is the ceiling.
  Secondes  metered time on the *account*, not the sum of these participations. A guest with no
            account has none, and an account whose trial was reset reads lower than the
            conversations it actually held.

Sent as both plain text and HTML. The text part is the one to trust: it is generated from the
same rows and survives a mail client that refuses the markup.
"""
import html
import logging

import boto3
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.config import settings
from src.models.salon_event import SalonEvent
from src.models.user import User
from src.services import livekit_service

logger = logging.getLogger(__name__)

COLUMNS = [
    "Contact",
    "Rôle",
    "Salons",
    "Langue",
    "Appareil",
    "Pays",
    "Vu en dernier",
    "Secondes cumulées",
    "Micro",
]


def _label(identity: str) -> str:
    """A readable name for somebody with no contact details.

    Guests join as "guest-<invitation id>", and the room shows them a short label derived from
    that same id — so the report can show what the other participants saw rather than a UUID
    nobody can place. Anything else is returned as-is: a reconstructed "legacy:" identity is
    more useful shown than hidden.
    """
    if identity.startswith("guest-"):
        return livekit_service.guest_display_name(identity[len("guest-"):])
    return identity


def collect(db: Session) -> list[dict]:
    """One row per person, newest first.

    Grouped on the identity pair rather than on the email alone: a guest reached only by text
    message has no address, and grouping on one column would fold every one of them together.
    """
    grouped = (
        db.query(
            SalonEvent.participant_identity,
            func.max(SalonEvent.email).label("email"),
            func.max(SalonEvent.phone).label("phone"),
            func.count(func.distinct(SalonEvent.salon_name)).label("salons"),
            func.max(SalonEvent.entered_at).label("last_seen"),
        )
        .group_by(SalonEvent.participant_identity)
        .order_by(func.max(SalonEvent.entered_at).desc())
        .all()
    )
    if not grouped:
        return []

    # Grouped on the LiveKit identity, not on the contact details. That is what puts anonymous
    # guests in the report at all: they have no address, and grouping on one would fold every
    # one of them into a single empty row.
    #
    # A consequence to expect: a host has one identity — their account UUID — so their salons
    # still aggregate into one line. A guest gets a fresh identity per invitation, so somebody
    # invited to three salons appears three times. That is what the rooms saw.
    people = [row.participant_identity for row in grouped]
    on_page = SalonEvent.participant_identity.in_(people)

    # Three small lookups instead of aggregating arrays in SQL, restricted to the people in the
    # report so their cost follows the report and not the size of the table.
    roles: dict[str, set[str]] = {}
    languages: dict[str, set[str]] = {}
    devices: dict[str, set[str]] = {}
    heard: set[str] = set()
    countries: dict[str, set[str]] = {}

    for identity, value in (
        db.query(SalonEvent.participant_identity, SalonEvent.user_type)
        .filter(on_page)
        .distinct()
    ):
        roles.setdefault(identity, set()).add(value)
    for identity, value in (
        db.query(SalonEvent.participant_identity, SalonEvent.first_spoken_language)
        .filter(on_page, SalonEvent.first_spoken_language.isnot(None))
        .distinct()
    ):
        languages.setdefault(identity, set()).add(value)
    for identity, value in (
        db.query(SalonEvent.participant_identity, SalonEvent.device_type)
        .filter(on_page, SalonEvent.device_type != "")
        .distinct()
    ):
        devices.setdefault(identity, set()).add(value)
    for (identity,) in (
        db.query(SalonEvent.participant_identity)
        .filter(on_page, SalonEvent.microphone_enabled.is_(True))
        .distinct()
    ):
        heard.add(identity)
    for identity, value in (
        db.query(SalonEvent.participant_identity, SalonEvent.country)
        .filter(on_page, SalonEvent.country != "")
        .distinct()
    ):
        countries.setdefault(identity, set()).add(value)

    # Metered time lives on the account, so it is looked up by address and is simply absent for
    # a guest who never registered. Matched on email only: an account is an address here.
    addresses = [row.email for row in grouped if row.email]
    seconds: dict[str, int] = {}
    if addresses:
        for email, trial, billed in db.query(
            User.email, User.trial_seconds_used, User.billed_seconds
        ).filter(User.email.in_(addresses)):
            seconds[email] = (trial or 0) + (billed or 0)

    rows = []
    for row in grouped:
        key = row.participant_identity
        rows.append(
            {
                # An address when there is one, a number when there is not, and otherwise the
                # room label this identity wore — "Guest 3F2A". Never a bare UUID: the point of
                # the report is that somebody can recognise who a line is about.
                "Contact": row.email or row.phone or _label(key),
                "Rôle": " + ".join(sorted(roles.get(key, set()))) or "—",
                "Salons": row.salons,
                "Langue": ", ".join(sorted(languages.get(key, set()))) or "—",
                "Appareil": ", ".join(sorted(devices.get(key, set()))) or "—",
                "Pays": ", ".join(sorted(countries.get(key, set()))) or "—",
                "Vu en dernier": row.last_seen.strftime("%Y-%m-%d %H:%M") if row.last_seen else "—",
                # A dash rather than a zero when there is no account: zero would claim somebody
                # held conversations of no length, which is a different statement.
                "Secondes cumulées": seconds.get(row.email, "—") if row.email else "—",
                # Read against Langue: a microphone that worked with no language heard is
                # somebody who tried and was not understood, which is a different problem from
                # somebody who never tried.
                "Micro": "oui" if key in heard else "non",
            }
        )
    return rows


_CAVEAT_TEXT = (
    "Micro : le microphone a fonctionne au moins une fois. Non + aucune langue = jamais essaye ; "
    "oui + aucune langue = a essaye sans etre entendu.\n"
    "Pays : region du navigateur, declaree par l'appareil. Rien ne collecte de position.\n"
    "Secondes cumulees : temps mesure sur le COMPTE, pas la somme de ces participations. "
    "Absent pour un invite sans compte, et plus bas que la realite si l'essai a ete remis a zero."
)


def as_text(rows: list[dict]) -> str:
    if not rows:
        return "Aucune participation enregistree.\n"
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in COLUMNS}
    header = "  ".join(c.ljust(widths[c]) for c in COLUMNS)
    body = "\n".join(
        "  ".join(str(r[c]).ljust(widths[c]) for c in COLUMNS) for r in rows
    )
    return f"{len(rows)} contacts\n\n{header}\n{'-' * len(header)}\n{body}\n\n{_CAVEAT_TEXT}\n"


def as_html(rows: list[dict]) -> str:
    """Escaped throughout: these are addresses supplied by strangers, and one of them landing
    unescaped in a mail client is an injection into the administrator's own inbox."""
    if not rows:
        return "<p>Aucune participation enregistrée.</p>"
    head = "".join(f"<th align='left'>{html.escape(c)}</th>" for c in COLUMNS)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(r[c]))}</td>" for c in COLUMNS) + "</tr>"
        for r in rows
    )
    return (
        f"<p><strong>{len(rows)} contacts</strong></p>"
        "<table cellpadding='6' cellspacing='0' border='1' "
        "style='border-collapse:collapse;font-family:sans-serif;font-size:13px'>"
        f"<thead style='background:#7B1528;color:#F8F3E8'><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table>"
        f"<p style='font-size:12px;color:#6b6257'>{html.escape(_CAVEAT_TEXT)}</p>"
    )


def send(db: Session, recipient: str) -> dict:
    """Build the report and mail it. Never raises: a failed report is not worth an alarm."""
    rows = collect(db)
    try:
        boto3.client("ses", region_name=settings.aws_region).send_email(
            Source=settings.ses_from_address,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": f"Vocaliz — {len(rows)} contacts", "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": as_text(rows), "Charset": "UTF-8"},
                    "Html": {"Data": as_html(rows), "Charset": "UTF-8"},
                },
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Participant report to %s failed: %s", recipient, exc, exc_info=True)
        return {"status": "send_failed", "contacts": len(rows)}
    # The count, never the addresses: writing them to CloudWatch would copy the personal data
    # into a second store with its own retention.
    logger.info("Participant report sent to %s (%d contacts)", recipient, len(rows))
    return {"status": "ok", "contacts": len(rows)}
