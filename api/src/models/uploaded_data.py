import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class UploadedData(Base):
    """Accounting: what each salon was given, and what it weighed.

    One row per source handed to a salon's agent. The question it answers is what a
    conversation cost and what it was about — nothing here drives behaviour.

    It exists because the schema records sources in two places and measures them in
    neither: a salon's first source lives on the salons row, later ones in
    salon_sources, and neither carries a size.

    This was briefly designed as a cache keyed on xAI file ids, to reuse embeddings across
    salons. That was dropped: a salon has one source and lasts ten minutes, so there is no
    corpus to retrieve from and nothing to embed. content_hash survives because it costs
    almost nothing and is the one column that would be needed to make this a cache later.

    Encryption at rest is the Aurora cluster's, as for salon_events: KMS covers the
    storage, its snapshots and its backups.
    """

    __tablename__ = "uploaded_data"

    file_id: Mapped[str] = mapped_column(
        String(128), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    salon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False
    )

    # SHA-256 of the extracted text. Not used for anything today; it is what a future
    # cache would look up, and computing it now costs one pass over a string we already
    # hold in memory.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # A source is a URL or a file, never both; each is null for the other kind.
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Reported by whoever counted them — the summariser returns a usage figure. Null when
    # nothing counted. Never inferred from character counts.
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Characters of extracted text, the unit the sources endpoint already reports as
    # contentLength. Not bytes: two different units under one name is how sizes stop
    # meaning anything.
    content_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Provenance, when the page said so. All three are optional and absent is ordinary: a
    # personal blog names no publisher, plenty of pages carry no date, and an uploaded file
    # carries none of it.
    #
    # article_date is a timestamp rather than the string the page wrote, because ordering is
    # the only reason it exists. A date nothing can sort is not a date.
    article_date: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    author: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    publisher: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    uploaded_by: Mapped[str] = mapped_column(String(320), nullable=False)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
