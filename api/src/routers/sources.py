"""Searching the consented corpus — sources hosts chose to publish to the platform.

Cross-salon by nature, which is why it is not under /salons: the point is to reach
material somebody else supplied. What makes that safe is not a check in this file but the
table it reads — shared_sources holds only what a host explicitly published, so a query
here cannot reach a private document however it is written.

Authentication is still required. The corpus is shared between hosts, not with the
internet, and an unauthenticated search endpoint over uploaded material would be a
crawlable index of it.
"""
import logging
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session as DbSession

from src.database import get_db
from src.dependencies.auth import get_current_user
from src.models.shared_source import SharedSource, SharedSourceConsent
from src.models.user import User
from src.rate_limit import limiter
from src.services import shared_source_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/search")
@limiter.limit("60/minute")
def search_shared_sources(
    request: Request,
    q: str = Query(..., min_length=2),
    limit: int = Query(3, ge=1, le=10),
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Published sources that bear on a question, best first.

    Called by the agent with the host's token when a participant asks about something the
    salon's own sources do not cover. Three results by default, because the answer is
    spoken: a list of ten is not something anyone can listen to.

    Summaries only. The full text of a result is fetched separately, and only if a
    participant asks about a detail the summary did not carry.
    """
    return {
        "query": q,
        "results": shared_source_service.search(db, q, limit=limit),
    }


@router.get("/{source_id}/excerpts")
@limiter.limit("60/minute")
def shared_source_excerpts(
    request: Request,
    source_id: str,
    q: str = Query(..., min_length=2),
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Passages of one published source that bear on a question.

    The follow-up to a search: a summary was read out, a participant asked about a figure
    it did not include, and the whole text is consulted only now.
    """
    try:
        parsed = _uuid.UUID(source_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Source not found.")

    if db.get(SharedSource, parsed) is None:
        raise HTTPException(status_code=404, detail="Source not found.")

    return {
        "sourceId": source_id,
        "query": q,
        "excerpts": shared_source_service.excerpts(db, parsed, q),
    }


@router.get("/mine")
def my_shared_sources(
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """What this host has published, so they can see it and take it back.

    Consent that cannot be reviewed is not consent. This is the screen that makes the
    checkbox meaningful.
    """
    # Joined through the consents, because that is where a person's agreement lives. The
    # page itself has no owner — two hosts may have published the same article, and
    # neither of them owns it.
    rows = (
        db.query(SharedSource, SharedSourceConsent.shared_at)
        .join(SharedSourceConsent, SharedSourceConsent.source_id == SharedSource.id)
        .filter(SharedSourceConsent.shared_by == (current_user.email or "").lower())
        .order_by(SharedSourceConsent.shared_at.desc())
        .all()
    )
    return {
        "sources": [
            {
                "sourceId": str(row.id),
                "url": row.url,
                "author": row.author or "",
                "publisher": row.publisher or "",
                "articleDate": row.article_date.isoformat() if row.article_date else None,
                "topics": list(row.topics or []),
                # When *this host* published it, not when the page entered the corpus.
                "sharedAt": shared_at.isoformat() if shared_at else None,
            }
            for row, shared_at in rows
        ]
    }


@router.delete("/{source_id}", status_code=200)
def withdraw_shared_source(
    source_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Take one of your own publications out of the corpus.

    A delete rather than a flag: consent withdrawn has to mean the material is gone, not
    that it sits behind a condition some future query might fail to apply.

    404 for someone else's source, not 403 — whether a given id exists in the corpus is
    not something one host needs to learn about another.
    """
    try:
        parsed = _uuid.UUID(source_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Source not found.")

    if not shared_source_service.withdraw(
        db, shared_by=current_user.email or "", source_id=parsed
    ):
        raise HTTPException(status_code=404, detail="Source not found.")

    logger.info("Host %s withdrew a shared source", current_user.email)
    return {"withdrawn": True}


@router.get("/topics")
@limiter.limit("60/minute")
def top_topics(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    db: DbSession = Depends(get_db),
):
    """What the published corpus is about, most common first.

    Unauthenticated, unlike everything else here, because it is shown at the top of the host
    page before anyone signs in. What it exposes is a list of subject words and how many
    public web pages carry each — no addresses, no summaries, and nothing from a source
    somebody kept private. That is the same class of information as a trending list on any
    site.

    One thing it does reveal: what the people using Vocaliz are reading about. Harmless in
    aggregate, and less so while there are few of them — with a handful of hosts this is a
    portrait of those few rather than of a population.
    """
    return {"topics": shared_source_service.top_topics(db, limit=limit)}
