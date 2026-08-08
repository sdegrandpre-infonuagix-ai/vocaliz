"""The consented corpus: web pages a host chose to make searchable by everyone.

Two properties make this safe, and both are structural rather than enforced by care.

Only what was consented to exists here. Sources live in two places — the first on the
salons row, later ones in salon_sources — so a cross-platform search over those would
have to query both and never once forget the filter. One missing WHERE would expose every
private document. Here, not sharing is a row that does not exist, and withdrawing consent
is a delete.

Only URLs can be here at all. There is no filename column and no file type, so an
uploaded document cannot be published even by a mistake in the code that calls this. A URL
points at something already public: indexing its summary tells nobody anything they could
not read by following the link. A file is the opposite — someone chose to hand it to us —
and no checkbox is worth the chance of getting that wrong.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base

# JSONB on Postgres, plain JSON on the SQLite the tests run against.
StringList = JSON().with_variant(JSONB(), "postgresql")


class SharedSource(Base):
    """One public web page, published to the platform."""

    __tablename__ = "shared_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Required, and the only kind of source that can be here. Its presence is what makes
    # publishing an uploaded file impossible rather than merely forbidden.
    url: Mapped[str] = mapped_column(Text, nullable=False)

    # What another agent reads aloud. The summary rather than the full text, because a
    # search result has to be speakable in a sentence or two.
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The extracted text, for the detailed follow-up a summary cannot answer. Kept rather
    # than re-fetched: the page may have changed or gone, and an answer drawn from what the
    # salon actually read is the honest one.
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Ten lowercased topics, extracted once at publication. This is what a spoken question
    # is matched against: "the latest on the USA and Iran" has to reach a page nobody
    # tagged by hand.
    #
    # Named topics rather than keywords because ads.topic already exists and these two are
    # meant to be compared — an ad about coffee should reach a page whose topics include
    # coffee. Two names for one idea is how a query ends up joining the wrong pair.
    topics: Mapped[list] = mapped_column(StringList, nullable=False, default=list)

    # Provenance, when the page said so. Optional, and absent is ordinary. Returned with
    # every search result: an agent about to read a summary aloud should be able to say who
    # published it and when, and a claim with no attribution is worth less than one with.
    #
    # article_date doubles as the recency signal. "The latest news on X" asks when the
    # article was written, not when a host happened to paste it — ranking on the paste date
    # is a proxy that fails in exactly the case that matters.
    article_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    author: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    publisher: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    # SHA-256 of the text, and the page's real identity — two URLs can serve the same
    # article. Unique, so the corpus never spends two of an agent's three results saying
    # the same thing.
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    # When the page entered the corpus, and when it was last published by anyone.
    #
    # Recency is part of relevance, not metadata: "the latest news on X" asks about time as
    # much as about subject. Ranking uses the second — a page another host publishes again
    # today is topical again today, and the first arrival is only a historical fact.
    first_shared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_shared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("trim(url) <> ''", name="ck_shared_sources_url"),
        CheckConstraint("trim(content_hash) <> ''", name="ck_shared_sources_hash"),
        # A row with neither a summary nor text would be found by a search and then have
        # nothing to say.
        CheckConstraint(
            "trim(summary) <> '' OR trim(content) <> ''",
            name="ck_shared_sources_has_something",
        ),
    )


class SharedSourceConsent(Base):
    """One host's agreement that one page may be searched by everyone.

    Separate from the page because consent belongs to a person and the page does not. Two
    hosts may publish the same article; the first withdrawing must not remove material the
    second still stands behind. Sharing prevails — the page stays in the corpus while any
    consent remains, and goes when the last one does.

    The salon is recorded here rather than on the page, because it describes *this
    host's* publication: the same article may reach the corpus from two unrelated
    conversations.
    """

    __tablename__ = "shared_source_consents"

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shared_sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # An email, shown to nobody. It exists so a host can review and withdraw their own
    # publications, and so a complaint can be traced to whoever published the material.
    shared_by: Mapped[str] = mapped_column(String(320), primary_key=True)

    salon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False
    )
    shared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
