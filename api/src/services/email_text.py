"""Bilingual formatting for outbound email.

Every message Salon sends goes out in English and then French, in one email. The
recipient's language is not knowable at send time — a guest is invited by address alone
and has no account, no profile and no stored preference — so picking one language would
be a guess, and guessing wrong on the invitation means the link does not get used.

Kept in one place so the two senders (OTP, invitations) cannot drift into different
layouts: a reader who has learned to scroll past the English half should find the French
half in the same spot in every message.
"""

SEPARATOR = "—" * 40


def bilingual_subject(en: str, fr: str) -> str:
    """Join both subjects on one line, English first.

    Mail clients truncate long subjects, which is precisely why English leads and the
    separator is a thin one: what survives truncation should still be a whole subject.
    """
    return f"{en} · {fr}"


def bilingual_body(en: str, fr: str) -> str:
    """Stack both bodies, English first, with a visible rule between them."""
    return f"{en}\n\n{SEPARATOR}\n\n{fr}"
