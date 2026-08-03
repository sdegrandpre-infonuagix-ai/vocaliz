"""A telephone code is six DIGITS, not six characters.

The previous constraint only checked the length, which let "12a456" through. A keypad
cannot enter a letter, so such a code would be one nobody could ever dial — stored,
reserved, and unreachable.

The expression is a chain of replaces rather than a regular expression, and that is
deliberate. Postgres would write `code ~ '^[0-9]{6}$'` and SQLite
`code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'` — two different strings meaning the same
thing, one enforced in production and the other in the tests, free to drift apart the day
somebody edits one of them. Stripping every digit and requiring nothing to remain is
uglier and runs identically on both, so the rule is verified by the tests exactly as
production enforces it.

Revision ID: 024
Revises: 023
Create Date: 2026-08-03
"""
from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

CODE_DIGITS = 6


def digits_only(column: str) -> str:
    """A CHECK expression asserting that `column` holds nothing but digits.

    Shared with the model so the two cannot disagree.
    """
    expression = column
    for digit in "0123456789":
        expression = f"replace({expression}, '{digit}', '')"
    return f"length({expression}) = 0"


def upgrade() -> None:
    op.drop_constraint("ck_code_available_length", "code_available", type_="check")
    op.create_check_constraint(
        "ck_code_available_digits",
        "code_available",
        f"length(code) = {CODE_DIGITS} AND {digits_only('code')}",
    )


def downgrade() -> None:
    op.drop_constraint("ck_code_available_digits", "code_available", type_="check")
    op.create_check_constraint(
        "ck_code_available_length", "code_available", f"length(code) = {CODE_DIGITS}"
    )
