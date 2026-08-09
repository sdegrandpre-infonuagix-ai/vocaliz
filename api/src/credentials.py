"""A username and a password, as a third way in (Story 10.7 / FR65).

Every other route runs through an identifier: a code to an address, a code to a number. That
works until somebody loses both — a changed job, a lost telephone, a closed mailbox — and then
the account, the paid balance and the gifted credit are gone, with no way left to prove they
were ever theirs.

So this is a **third** route and never a replacement. Both stay open, because the failure this
one covers is precisely that the other stopped working.

Hashing uses `hashlib.scrypt` from the standard library: memory-hard, salted per password, and
already present wherever Python is. Reaching for bcrypt or argon2 would mean adding a compiled
dependency to a Lambda bundle, which is a packaging decision rather than a security one — and
scrypt is the right tool regardless.

The stored value carries its own salt and parameters. A salt in a second column is a salt
somebody migrates without, and a cost factor that lives only in this file cannot be raised
without invalidating every hash written under the old one.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re

from sqlalchemy.orm import Session

from src.models.user import User

# Three characters is a handle somebody is stuck with; letters, digits, dots, dashes and
# underscores are what survives being read aloud, typed on a telephone and put in a URL. A
# space is the one that produces a support call about a login that "does nothing".
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")

# Length rather than a character-class rule. Forcing a symbol and a capital produces
# `Password1!` on every account; length is what actually costs an attacker anything.
MINIMUM_PASSWORD_CHARACTERS = 8

# scrypt at the parameters OWASP suggests for interactive logins. Written into the stored
# value so raising them later does not invalidate what is already there.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16


class CredentialsRefused(ValueError):
    """A username or password that cannot be accepted, with the reason named."""


def normalise_username(value: str | None) -> str:
    """One handle, however it was typed.

    Lowercased and trimmed. `Marie` and `marie` as two accounts is two people who each think
    they are the only one, and a sign-in that depends on which shift key was pressed.
    """
    return (value or "").strip().lower()


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """A salted scrypt hash, carrying everything needed to check it again.

    `scrypt$n$r$p$salt$hash`. Self-describing on purpose: the salt is not a second column to
    forget, and the cost factors travel with the value so they can be raised for new
    passwords without invalidating old ones.
    """
    salt = salt if salt is not None else os.urandom(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Whether this password produced that stored value.

    Anything unreadable verifies as **false** rather than raising. A row written by hand, or
    by an older scheme, must not turn the sign-in path into an outage — and "not this
    password" is the honest answer either way.

    Compared with `compare_digest`, so the time taken says nothing about how much of the hash
    was right.
    """
    if not stored or not password:
        return False
    try:
        scheme, n, r, p, salt_hex, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived.hex(), expected)


def set_credentials(db: Session, person: User, *, username: str, password: str) -> User:
    """Give this account a handle and a password, or say why not."""
    handle = normalise_username(username)
    if not USERNAME_PATTERN.match(handle):
        raise CredentialsRefused(
            f"{username!r} cannot be a username. Use 3 to 32 characters — letters, digits, "
            "dots, dashes or underscores — starting with a letter or a digit."
        )
    if len(password or "") < MINIMUM_PASSWORD_CHARACTERS:
        raise CredentialsRefused(
            f"A password needs at least {MINIMUM_PASSWORD_CHARACTERS} characters. "
            "Length is what makes one hard to guess."
        )

    taken = db.query(User).filter(User.username == handle).first()
    if taken is not None and taken.id != person.id:
        raise CredentialsRefused(
            f"{handle} is already taken. Choose another and try again."
        )

    person.username = handle
    person.password_hash = hash_password(password)
    return person


def sign_in(db: Session, *, username: str, password: str) -> User | None:
    """The account behind this handle and password, or nobody.

    `None` for every failure, and deliberately not a reason: telling somebody the username
    exists but the password is wrong is telling an attacker which half to keep working on.
    """
    person = db.query(User).filter(User.username == normalise_username(username)).first()
    if person is None:
        return None
    if not verify_password(password, person.password_hash):
        return None
    return person
