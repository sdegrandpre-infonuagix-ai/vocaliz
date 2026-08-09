"""Count what is in the database, and empty it when asked.

Two operations that belong together: nobody should be able to empty a table without
having been able to see what was in it first. The census is read-only and the emptying
refuses to run without an explicit written confirmation, because there is no undo beyond
a point-in-time restore.

Three groups, because "all tables" means different things and the difference matters:

  DATA        what users and conversations produced. This is what emptying is usually for.
  REFERENCE   seeded, not produced — the telephone-code pool, the ad regions, the house
              ads. Emptying these does not reset the platform, it breaks it: invitations
              stop being able to reserve a code and ad targeting has nothing to match.
  SCHEMA      alembic_version. Emptying it makes every migration run again on a database
              that already has them applied, which fails on the first CREATE TABLE.
"""
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

logger = logging.getLogger(__name__)

# Ordered child-to-parent so a plain DELETE would work too; TRUNCATE ... CASCADE does not
# need it, but the order documents the dependency and makes a dry run readable.
DATA = [
    "utterance_translations",
    "utterances",
    "ad_broadcasts",
    "billing_events",
    "salon_events",
    "shared_source_consents",
    "shared_sources",
    "uploaded_data",
    "salon_sources",
    "invitations",
    "friends",
    "salons",
    "users",
    "service_health",
]

REFERENCE = [
    "code_available",
    "ads_regions",
    "ads",
    "advertisers_regions",
    "advertisers",
    "region_google_plus_codes",
    "regions",
]

CONFIRMATION = "EMPTY ALL TABLES"


def census(db: DbSession) -> dict:
    """Row counts per table. Read-only, and the thing to run before emptying anything."""
    counts = {}
    for table in DATA + REFERENCE + ["alembic_version"]:
        try:
            counts[table] = db.execute(text(f"SELECT count(*) FROM {table}")).scalar()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            counts[table] = f"error: {exc.__class__.__name__}"
    return {
        "data": {t: counts[t] for t in DATA},
        "reference": {t: counts[t] for t in REFERENCE},
        "schema": {"alembic_version": counts["alembic_version"]},
        "dataRows": sum(v for v in (counts[t] for t in DATA) if isinstance(v, int)),
        "referenceRows": sum(v for v in (counts[t] for t in REFERENCE) if isinstance(v, int)),
    }


def truncate(db: DbSession, *, confirm: str, include_reference: bool = False) -> dict:
    """Empty the data tables, and the reference tables only if explicitly asked.

    Requires the exact confirmation string. A boolean flag is too easy to send by accident
    from a shell; a sentence has to be typed on purpose.

    alembic_version is never touched. TRUNCATE ... CASCADE in one statement so no foreign
    key is ever momentarily violated, and RESTART IDENTITY so sequences do not carry
    numbering over from data that no longer exists.
    """
    if confirm != CONFIRMATION:
        return {
            "status": "refused",
            "reason": f'confirm must be exactly "{CONFIRMATION}"',
            "truncated": [],
        }

    before = census(db)
    tables = DATA + (REFERENCE if include_reference else [])

    try:
        db.execute(
            text(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Truncate failed")
        return {"status": "failed", "error": str(exc), "truncated": []}

    logger.warning(
        "Emptied %d tables (%d data rows, reference %s)",
        len(tables),
        before["dataRows"],
        "included" if include_reference else "kept",
    )
    return {
        "status": "emptied",
        "truncated": tables,
        "rowsRemoved": before["dataRows"]
        + (before["referenceRows"] if include_reference else 0),
        "referenceKept": not include_reference,
        "after": census(db),
    }
