from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class SalonEvent(Base):
    """One participation: who was in which salon, for how long, and how it went.

    Encryption at rest is the Aurora cluster's, not this table's — the storage is
    KMS-encrypted, which covers snapshots and backups too. Nothing here is encrypted at
    the column level, so anyone holding SQL access reads these values in clear. That was
    a deliberate choice: column encryption would have forced a deterministic scheme on the
    key columns and ruled out every query but equality.

    The row still holds personal data — an email or a phone number, and sometimes an
    approximate position. It deserves a retention rule; there is none yet.
    """

    __tablename__ = "salon_events"

    # Composite key: one row per person, per role, per salon. Re-entering the same salon
    # updates that row rather than adding a second one — a participation, not a visit log.
    #
    # IP and GPS were initially meant to be part of this key. They are not, and could not
    # be: a primary key column cannot be NULL, and the position is missing whenever the
    # browser refuses it.
    # Identity is two columns because a guest may be invited by text message alone and
    # have no address at all. Neither can be NULL — a primary key column cannot be — so
    # the absent one is an empty string, and that sentinel has to be respected everywhere:
    # to the database '' is a value like any other, so "has an email" is `<> ''` and never
    # `IS NOT NULL`. A single lapse would quietly create a second row for one person.
    #
    # The CHECK below makes the one intolerable state impossible: both empty, a
    # participation attached to nobody.
    #
    # Expect this consequence: someone invited by email to one salon and by text to
    # another is two identities here, not one. Reconciling them would need a rule for
    # deciding that an address and a number belong to the same person, and there is none.
    # The LiveKit identity, which is what the room actually saw. A host joins as their account
    # UUID, a guest as "guest-<invitation id>", and both exist before the participant connects.
    #
    # This is the key because an anonymous invitation has no address and no number: keyed on
    # those, such a participation could not be stored at all, and was not — anonymous guests
    # joined salons and appeared nowhere. An identity is present whether or not anybody knows
    # who the person is, which is exactly the property a key needs here.
    #
    # user_type is deliberately no longer part of the key: one identity is one participant in
    # one salon, and the same identity cannot be both host and guest of it.
    participant_identity: Mapped[str] = mapped_column(String(200), primary_key=True)
    salon_name: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Who they are, when that is known. Ordinary columns now rather than key material: they say
    # how to reach somebody, which is a different question from which participant a row is
    # about. Empty for an anonymous guest, and for a guest reached only by text the email is
    # empty while the phone is not.
    email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    user_type: Mapped[str] = mapped_column(String(5), nullable=False)

    # Where they were, to the nearest cell of an Open Location Code grid — six digits by
    # default, about five and a half kilometres across. Encoded at ingestion, so the
    # precise coordinates never reach the disk.
    #
    # A Plus Code rather than rounded decimals because a decimal pair still reads as a
    # point, and a point invites being treated as one. This is a cell; the imprecision is
    # part of the value.
    #
    # Empty when the participant declined the location prompt, which is the common case.
    # There is no fallback: deriving a position from an IP address needs a GeoIP source
    # that does not exist here, and keeping the address in case one appeared one day
    # would be holding personal data against a plan rather than against a use.
    plus_code: Mapped[str] = mapped_column(String(16), nullable=False, default="")

    # What kind of device this person joined from, as one of a closed set of categories —
    # "iphone", "android-tablet", "windows" — and never the User-Agent header it came from.
    # The header carries browser build, engine version and often the exact model, which
    # together identify somebody across salons better than anything else here; a category
    # answers what the interface should assume and nothing about who.
    #
    # On the participation rather than the account, for the same reason as the language above:
    # the same person joins from a laptop at work and a phone on the train, and an account-level
    # column would keep only the last of those and call it a fact about them.
    #
    # Empty when nothing could be determined — a telephone participant has no device at all in
    # this sense. See device_service for why the classification comes from the browser rather
    # than from the header: Safari on iPad reports itself as a Macintosh.
    device_type: Mapped[str] = mapped_column(String(20), nullable=False, default="")

    # Two-letter country, from the browser's own locale — the region subtag of
    # navigator.language, so "fr-CA" gives CA. Self-reported and easily wrong: somebody
    # travelling, or running an English system in Montreal, reports whatever their device says.
    #
    # That ceiling is deliberate. Nothing here collects a position — no page asks the browser
    # for one — and the API is not behind CloudFront, so no viewer-country header arrives. The
    # alternatives were a GeoIP service on an address this schema pointedly does not keep, or
    # nothing at all.
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="")

    # Whether this participant's microphone ever worked. Reported by the client, which is the
    # only party that knows: the browser either granted the permission or refused it.
    #
    # Read together with first_spoken_language it separates two states that were previously
    # identical — somebody who never tried to speak, and somebody who tried and was not heard.
    # With real users those need opposite responses, and nothing distinguished them.
    #
    # Write-once and true-only: the fact worth keeping is that it worked at some point, not
    # whether it was still on at the end. Somebody who mutes themselves before leaving has
    # still been heard.
    microphone_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # A random UUID the browser keeps and sends back, so a device that returns is recognisable
    # as the same one. It answers a question nothing else could: an anonymous invitation mints a
    # fresh identity every visit, so one person coming five times looked like five people.
    #
    # Not a MAC address — no browser exposes one, and phones randomise theirs per network for
    # exactly this reason. Not a fingerprint either: probing canvas and fonts would work without
    # consent, which is why it carries a heavier legal regime than a value the person can delete.
    #
    # What it measures is a browser, not a human. Private browsing, cleared storage and a second
    # browser on one phone each read as a new device; two people sharing a laptop read as one.
    # Anywhere this is counted, that has to be said.
    device_token: Mapped[str] = mapped_column(
        String(36), nullable=False, default="", index=True
    )

    # BCP-47 code for the first language this person was heard speaking *in this salon* —
    # not the language of the interface they clicked through, and not a property of the
    # person. Someone may hold one conversation in French and the next in English, which
    # is why this lives on the participation rather than on the account.
    #
    # First rather than predominant, deliberately: "first heard" is a single event the
    # agent can report once and never revise, where "predominant" would need continuous
    # weighing and a rule for when the balance tips. The cost is that someone who opens in
    # English and continues in French is recorded as English — rare in ten minutes.
    #
    # Written once. A later report is ignored rather than overwriting, so the column
    # keeps meaning what its name says.
    first_spoken_language: Mapped[str | None] = mapped_column(String(10), nullable=True)

    entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    exited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Three states, and the third is not a failure: TRUE and FALSE are answers, NULL means
    # the question was never asked or never answered — a participant who simply closed
    # the tab. Collapsing NULL into FALSE would invent dissatisfaction that nobody voiced.
    enjoyed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        CheckConstraint("user_type IN ('host', 'guest')", name="ck_salon_events_user_type"),
        # A participation must be attached to somebody who was in the room. Weaker than the
        # old rule about contact details, and stronger about presence.
        CheckConstraint(
            "participant_identity <> ''", name="ck_salon_events_identified"
        ),
    )
