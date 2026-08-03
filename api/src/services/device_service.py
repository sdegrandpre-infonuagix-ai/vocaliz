"""What kind of device someone joined from, as a category and never as a fingerprint.

Only the classification is stored. The raw User-Agent header is not, and deliberately: it
carries browser build, engine version and often the exact device model, which together
identify a person across sessions far better than anything else we hold. The same reasoning as
the position — a neighbourhood-scale Plus Code rather than coordinates. A category answers
"what should the interface assume" and answers nothing about who.

The awkward truth this module exists to contain: **Safari on iPad reports itself as a
Macintosh**. Apple made desktop-class Safari the default on iPadOS 13, and the header says
"Macintosh; Intel Mac OS X" with nothing to distinguish it. No amount of header parsing fixes
that, so the browser is asked to decide instead — it can see `navigator.maxTouchPoints`, which
a real Mac reports as 0 — and this module classifies only when the client said nothing.
"""
import re

# The closed vocabulary. Anything outside it is refused rather than stored, so a client cannot
# turn this column into free text, and a query never has to guess at spellings.
KNOWN = frozenset(
    {
        "windows",
        "mac",
        "linux",
        "chromeos",
        "iphone",
        "ipad",
        "android-phone",
        "android-tablet",
        # When the family is clear but the platform is not, which is the honest answer for a
        # browser that only says "Mobile".
        "phone",
        "tablet",
        "desktop",
    }
)

# Absent is an empty string, not None: the same convention as the identity and position
# columns, so "unknown" compares in a query rather than behaving differently in every one.
UNKNOWN = ""


def normalise(value: str | None) -> str:
    """A client-supplied category, kept only if it is one we recognise."""
    if not value:
        return UNKNOWN
    candidate = value.strip().lower()
    return candidate if candidate in KNOWN else UNKNOWN


def classify(user_agent: str | None) -> str:
    """A category from the User-Agent header, for when the client offered none.

    A fallback, not the primary path. It cannot tell an iPad from a Mac — see the module
    docstring — and it will call a modern iPad "mac". Where that distinction matters, the
    client's own answer is the one to use.
    """
    if not user_agent:
        return UNKNOWN
    ua = user_agent.lower()

    # Order matters throughout: an Android tablet's header also contains "linux", an iPhone's
    # contains "mac os x", and Windows tablets claim "windows". The most specific claim wins.
    if "ipad" in ua:
        return "ipad"
    if "iphone" in ua or "ipod" in ua:
        return "iphone"
    if "android" in ua:
        # Android's own convention: a phone says "Mobile", a tablet omits it. Unreliable on
        # custom builds, which is why a tablet that lies is merely called a phone rather than
        # rejected.
        return "android-phone" if "mobile" in ua else "android-tablet"
    if "windows phone" in ua:
        return "phone"
    if "windows" in ua:
        return "windows"
    if "cros" in ua:
        return "chromeos"
    if "mac os" in ua or "macintosh" in ua:
        return "mac"
    if "linux" in ua:
        return "linux"
    # A browser that says only "Mobile" or "Tablet" still tells us the shape of the screen.
    if re.search(r"\btablet\b", ua):
        return "tablet"
    if "mobile" in ua:
        return "phone"
    return UNKNOWN


def resolve(claimed: str | None, user_agent: str | None) -> str:
    """The category to record: what the client said, or what the header suggests.

    The client wins when it speaks, because it is the only party that can tell an iPad from a
    Mac. This is telemetry rather than a security boundary — a participant who misreports their
    device skews a count and gains nothing — so the value is validated against the vocabulary
    and otherwise trusted.
    """
    return normalise(claimed) or classify(user_agent)
