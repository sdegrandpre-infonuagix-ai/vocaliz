"""Publishing a source to the platform, and finding one from a spoken question.

Two operations, both deliberately simple.

Publishing copies a source into shared_sources. Only what a host consented to exists here,
so a search cannot accidentally reach anything else — the safety property is the table's
contents, not a filter anyone has to remember.

Searching scores candidates in Python rather than in SQL. The corpus is small, the query
arrives as a spoken sentence rather than as terms, and ranking needs both topical overlap
and recency: "the latest news on the USA and Iran" is a question about time as much as
about subject. Postgres full-text search or embeddings would beat this once there are
thousands of sources; at the current size they would be machinery in search of a problem,
and neither would run on the SQLite the tests use.
"""
import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DbSession

from src.models.shared_source import SharedSource, SharedSourceConsent
from src.services import summary_service

logger = logging.getLogger(__name__)

# How many published sources are considered for one question. Bounded so a growing corpus
# cannot turn a spoken question into a slow one; the rows are read without their text, so
# the cost is a few hundred short rows rather than megabytes.
CANDIDATE_LIMIT = 500

# Words shorter than this carry no topic. Applied to the question, not to the keywords:
# "USA" is three characters and is exactly what someone would say.
MIN_QUERY_WORD = 3

# A match on a keyword is worth more than a match in the prose, because keywords were
# chosen as the terms a person would say out loud.
KEYWORD_WEIGHT = 3
SUMMARY_WEIGHT = 1

# Recency, in points added to a score, decaying over roughly a month. Enough to separate
# two equally relevant documents, not enough to float a stale match above a fresh one.
RECENCY_WEIGHT = 2.0
RECENCY_HALF_LIFE_DAYS = 30.0


def _words(text: str) -> set[str]:
    """The content words of a phrase, lowercased and stripped of punctuation."""
    return {
        w for w in re.split(r"[^\w\-]+", (text or "").lower()) if len(w) >= MIN_QUERY_WORD
    }


def publish(
    db: DbSession,
    *,
    session_id,
    shared_by: str,
    url: str,
    summary: str = "",
    content: str = "",
    keywords: list[str] | None = None,
    article_date=None,
    author: str = "",
    publisher: str = "",
) -> SharedSource | None:
    """Publish a public web page to the corpus, and record this host's consent.

    Only URLs. An uploaded file has no way in — there is no parameter for one and no column
    to hold it. A URL points at something already public; a file is something someone chose
    to hand us, and no checkbox is worth the chance of confusing the two.

    Deduplicated on the text, not the address: two URLs can serve the same article. When
    the page is already there this adds a consent rather than a second copy, and refreshes
    last_shared_at — a page brought up again today is topical again today.

    Sharing prevails on a duplicate. The page stays while any consent remains, so one host
    withdrawing cannot remove material another still stands behind.

    Best-effort: a failure here must not fail the upload that triggered it. The host keeps
    their source either way; only its searchability is lost.
    """
    url = (url or "").strip()
    summary = (summary or "").strip()
    content = (content or "").strip()
    if not url or (not summary and not content):
        return None

    digest = summary_service.content_hash(content or summary)
    now = datetime.now(tz=timezone.utc)

    try:
        row = db.query(SharedSource).filter(SharedSource.content_hash == digest).first()
        if row is None:
            row = SharedSource(
                url=url,
                summary=summary,
                content=content,
                keywords=summary_service.normalise_keywords(keywords or []),
                article_date=article_date,
                author=(author or "")[:200],
                publisher=(publisher or "")[:200],
                content_hash=digest,
                first_shared_at=now,
                last_shared_at=now,
            )
            db.add(row)
            db.flush()
        else:
            # Republished. The text is identical by definition of the hash, so nothing is
            # overwritten except the fact that somebody brought it up again.
            row.last_shared_at = now

        owner = (shared_by or "").lower()
        if db.get(SharedSourceConsent, (row.id, owner)) is None:
            db.add(
                SharedSourceConsent(
                    source_id=row.id, shared_by=owner, session_id=session_id, shared_at=now
                )
            )
        db.commit()
        db.refresh(row)
        return row
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not publish a source for session %s", session_id, exc_info=True)
        return None


def _score(row, query_words: set[str], now: datetime) -> float:
    """How well one published source answers a question.

    Substring matching in both directions, so "iran" finds "iranian" and a keyword
    "united states" is found by "states". Crude, and right often enough for a corpus this
    size — it is the summary the agent reads out, so a near miss costs a sentence rather
    than a wrong answer.
    """
    hits = 0
    for keyword in row.keywords or []:
        if any(w in keyword or keyword in w for w in query_words):
            hits += KEYWORD_WEIGHT

    prose = (row.summary or "").lower()
    hits += SUMMARY_WEIGHT * sum(1 for w in query_words if w in prose)

    if not hits:
        return 0.0

    # Recency only ever adds, and only to something that already matched. A fresh document
    # about nothing must never outrank an old one about the subject.
    #
    # The article's own date when the page gave one, falling back to when it was last
    # published here. The fallback is a proxy and is wrong precisely when a host shares
    # something old today — which is why the real date is preferred whenever it exists.
    shared_at = row.article_date or row.last_shared_at
    if shared_at is not None:
        if shared_at.tzinfo is None:
            shared_at = shared_at.replace(tzinfo=timezone.utc)
        age_days = max((now - shared_at).total_seconds() / 86400.0, 0.0)
        hits += RECENCY_WEIGHT * (0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS))

    return float(hits)


def search(db: DbSession, query: str, *, limit: int = 3) -> list[dict]:
    """Published sources that bear on a spoken question, best first.

    The full text is deliberately not loaded while ranking: candidates are read without
    it, and only the winners are fetched whole. A source can be fifty thousand characters,
    and scoring five hundred of them in memory would cost megabytes to answer one
    question.
    """
    words = _words(query)
    if not words:
        return []

    try:
        candidates = (
            db.query(
                SharedSource.id,
                SharedSource.url,
                SharedSource.summary,
                SharedSource.keywords,
                SharedSource.article_date,
                SharedSource.author,
                SharedSource.publisher,
                SharedSource.last_shared_at,
            )
            .order_by(SharedSource.last_shared_at.desc())
            .limit(CANDIDATE_LIMIT)
            .all()
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not search the shared corpus", exc_info=True)
        return []

    now = datetime.now(tz=timezone.utc)
    scored = [(row, _score(row, words, now)) for row in candidates]
    best = sorted(
        (pair for pair in scored if pair[1] > 0), key=lambda pair: pair[1], reverse=True
    )[:limit]

    return [
        {
            "sourceId": str(row.id),
            "url": row.url,
            "summary": row.summary,
            "keywords": list(row.keywords or []),
            # Attribution travels with the result. An agent reading a summary aloud should
            # be able to say where it came from, and a claim with no source is worth less.
            "articleDate": row.article_date.isoformat() if row.article_date else None,
            "author": row.author or "",
            "publisher": row.publisher or "",
            "sharedAt": row.last_shared_at.isoformat() if row.last_shared_at else None,
            # Rounded because it is shown to nobody and compared by no one; it exists so a
            # log can say why one result beat another.
            "score": round(score, 2),
        }
        for row, score in best
    ]


def excerpts(db: DbSession, source_id, query: str, *, max_excerpts: int = 3) -> list[str]:
    """Passages of one published source that bear on a question.

    The follow-up to a search: the agent read out a summary, a participant asked about a
    detail it did not carry, and the whole text is fetched only now.
    """
    try:
        row = db.get(SharedSource, source_id)
    except Exception:  # noqa: BLE001
        logger.warning("Could not read shared source %s", source_id, exc_info=True)
        return []
    if row is None or not row.content:
        return []
    return summary_service.search(row.content, query, max_excerpts=max_excerpts)


def withdraw(db: DbSession, *, shared_by: str, source_id) -> bool:
    """Withdraw one host's consent, and the page with it if no consent remains.

    A delete, not a flag. Consent withdrawn has to mean the material is gone, not that it
    sits behind a condition some future query might fail to apply.

    But only this host's consent. Another host who published the same article still stands
    behind it, and sharing prevails — removing the page would revoke a consent nobody
    withdrew.
    """
    try:
        consent = db.get(SharedSourceConsent, (source_id, (shared_by or "").lower()))
        if consent is None:
            return False
        db.delete(consent)
        db.flush()

        remaining = (
            db.query(SharedSourceConsent)
            .filter(SharedSourceConsent.source_id == source_id)
            .count()
        )
        if remaining == 0:
            row = db.get(SharedSource, source_id)
            if row is not None:
                db.delete(row)
        db.commit()
        return True
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not withdraw shared source %s", source_id, exc_info=True)
        return False
