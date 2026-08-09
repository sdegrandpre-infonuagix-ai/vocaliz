"""Grant a reactivation credit from the command line (FR67, Story 8.10).

    python -m src.cli.grant_credit --operator <uuid> --reason "february win-back" <user-id>...

Deliberately not a screen, not a route, and not an admin account. Access to production is the
access control. Nothing is written until the operator has seen the total and typed `yes`:
somebody about to issue currency should learn how much *before* the fact rather than from the
ledger afterwards.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone

from src.database import SessionLocal
from src.reactivation import confirmation_text, grant_to_cohort


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="grant_credit", description=__doc__)
    parser.add_argument("subject_ids", nargs="+", help="the people to credit")
    parser.add_argument("--operator", required=True, help="who is issuing this")
    parser.add_argument("--reason", required=True, help="why — recorded in the ledger")
    parser.add_argument(
        "--cents",
        type=int,
        default=None,
        help="amount each, in cents; the reactivation default applies when omitted",
    )
    parser.add_argument(
        "--yes", action="store_true", help="skip the prompt; the total is still printed"
    )
    return parser


def main(argv: list[str] | None = None, *, session_factory=SessionLocal, stdin=None) -> int:
    """Confirm, then write. Returns a process exit code."""
    from src.reactivation import REACTIVATION_CREDIT_CENTS

    args = build_parser().parse_args(argv)
    people = [uuid.UUID(one) for one in args.subject_ids]
    amount = REACTIVATION_CREDIT_CENTS if args.cents is None else args.cents

    print(confirmation_text(beneficiaries=len(people), amount_cents=amount))
    if not args.yes:
        answer = (stdin or sys.stdin).readline().strip().lower()
        if answer != "yes":
            print("Nothing was written.")
            return 1

    db = session_factory()
    try:
        grants = grant_to_cohort(
            db,
            subject_ids=people,
            reason=args.reason,
            operator_id=uuid.UUID(args.operator),
            amount_cents=args.cents,
            now=datetime.now(tz=timezone.utc),
        )
        db.commit()
    finally:
        db.close()

    granted = [one for one in grants if one.granted_cents]
    for refused in (one for one in grants if not one.granted_cents):
        print(f"refused {refused.subject_id}: {refused.refused_because}")
    print(f"granted to {len(granted)} of {len(people)}.")
    return 0


if __name__ == "__main__":  # pragma: no cover - the production entry point
    raise SystemExit(main())
