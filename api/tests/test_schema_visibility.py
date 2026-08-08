"""A constraint that exists only in a migration is a defect waiting for a user to find.

The test database is built from the models. Anything a migration creates and no model declares
therefore exists in production and nowhere else: no test can violate it, so code that violates
it passes every check and fails in front of somebody.

This is not hypothetical. `uq_invitations_phone_pin_pending` lived only in migration 022, and
the code that violated it shipped — every invitation on the platform answered 500, permanently,
because the telephone-code pool kept handing back the one code a pending row still owned. 615
tests passed while it was broken.

An earlier hand audit of this same question reported nothing wrong. It looked for constraints
and missed indexes, which is what `op.create_index(..., unique=True)` produces — so the one
that mattered was invisible to the audit as well as to the tests. Hence a test rather than an
audit: it runs every time, and it cannot decide to look at only half the schema.

Only *enforcing* objects are required. A plain index makes queries faster and can never fail a
write, so declaring it on the model would be tidiness, not safety — this deliberately does not
ask for that, because a check nobody can satisfy gets deleted rather than obeyed.

Scope, stated because a test that implies more coverage than it has is worse than none: this
reads `op.create_index` / `op.create_*_constraint` calls, which is the form that produced the
outage. Constraints written inline inside `op.create_table` are not compared, because the
models express many of them anonymously — `unique=True` on a column raises the same rule under
a generated name — and matching by name there reports differences that are not defects. The
two that exist (`uq_regions_name`, `uq_shared_sources_content_hash`) were checked by hand and
are both enforced by a column-level `unique=True`.
"""
import pathlib
import re

from src.database import Base
import src.main  # noqa: F401  — importing the app registers every model on the metadata

MIGRATIONS = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"

# Creates something a write can violate. A bare index is absent on purpose.
_ENFORCING = r"unique_constraint|check_constraint|foreign_key_constraint|primary_key_constraint"


def _declared_on_the_models() -> set[str]:
    names: set[str] = set()
    for table in Base.metadata.tables.values():
        names |= {index.name for index in table.indexes if index.name}
        names |= {c.name for c in table.constraints if c.name}
    return names


def _created_by_migrations() -> dict[str, tuple[str, str]]:
    """Name → (migration, kind), for everything still standing at head.

    Something a later migration drops is not in production, so requiring the models to declare
    it would mean declaring things that do not exist.
    """
    created: dict[str, tuple[str, str]] = {}
    dropped: set[str] = set()

    for path in sorted(MIGRATIONS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        # Only what upgrade() does. Almost every downgrade() drops what its own upgrade
        # created, so reading the whole file makes every constraint in the project look
        # dropped — and the census then finds nothing and reports all is well.
        text = text.split("def downgrade", 1)[0]
        for match in re.finditer(
            rf'op\.create_(index|{_ENFORCING})\(\s*\n?\s*"([^"]+)"(.{{0,400}}?)\n\s*\)',
            text,
            re.S,
        ):
            kind, name, body = match.group(1), match.group(2), match.group(3)
            if kind == "index" and "unique=True" not in body:
                continue      # performance only; cannot fail a write
            created[name] = (path.name, "unique index" if kind == "index" else kind)
        for match in re.finditer(r'op\.drop_(?:index|constraint)\(\s*\n?\s*"([^"]+)"', text):
            dropped.add(match.group(1))
        # A renamed object is the same object under a new name, and the models only ever
        # declare the current one. Without this the census would report the old name as
        # existing in production forever — and, worse, miss the new name entirely, so a
        # constraint could be renamed out of sight of the very test that guards it.
        for match in re.finditer(
            r'ALTER INDEX (\w+) RENAME TO (\w+)', text
        ):
            old, new = match.group(1), match.group(2)
            if old in created:
                origin, kind = created.pop(old)
                created[new] = (f"{origin} → {path.name}", kind)

    return {name: v for name, v in created.items() if name not in dropped}


def test_every_enforcing_constraint_is_visible_to_the_tests():
    created = _created_by_migrations()
    declared = _declared_on_the_models()
    invisible = {name: created[name] for name in created if name not in declared}

    assert not invisible, (
        "these exist in production and in no test database, so nothing can catch code that "
        "violates them:\n"
        + "\n".join(f"  {mig}: {kind} {name}" for name, (mig, kind) in sorted(invisible.items()))
    )


def test_the_census_actually_reads_the_migrations():
    """Guards the regexes. Both halves returning empty would make the test above pass by
    finding nothing to compare — which is how the hand audit reached the wrong answer, and
    how the first version of this test passed while reading nothing at all.

    Named objects rather than a count: a threshold survives a pattern that has quietly
    stopped matching one of the two forms."""
    created = _created_by_migrations()
    for expected in (
        "uq_utterances_salon_sequence",          # op.create_index(unique=True)
        "ck_advertisers_company_not_blank",        # op.create_check_constraint
        "ck_users_caption_scale",                  # the most recent of them
    ):
        assert expected in created, f"{expected} not found; the migration pattern broke"
    assert len(_declared_on_the_models()) > 10, "no models registered on the metadata"


def test_the_constraint_behind_the_outage_is_among_them():
    """A named regression. If this index ever stops being found, the test above has gone
    blind to the exact shape that took invitations down."""
    assert "uq_invitations_phone_pin_pending" in _created_by_migrations()
    assert "uq_invitations_phone_pin_pending" in _declared_on_the_models()
