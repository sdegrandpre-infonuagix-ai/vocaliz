"""Guest web router — serves the browser join page for guests without an account."""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["guest"])

_WEB_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "web")
)


@router.get("/join/{join_token}", include_in_schema=False)
def guest_join_page(join_token: str):
    """Serve the browser join page. Token validation happens client-side via the API."""
    return FileResponse(os.path.join(_WEB_DIR, "join.html"), media_type="text/html")


@router.get("/host", include_in_schema=False)
def host_console_page():
    """Serve the host console.

    The PRD gives the host a native app; this browser console exists because that app
    has no room screen yet, leaving no way at all to add a source mid-session (FR3) or
    generate an invitation. It authenticates with the same email OTP as the app, so it
    grants nothing the host does not already have.
    """
    return FileResponse(os.path.join(_WEB_DIR, "host.html"), media_type="text/html")


# The pages whose dictionaries can be requested, and the languages that exist as generated
# files. Allowlists rather than a constructed path: `../../secret` in a language name would
# otherwise serve any file in the container, and a check for ".." is the kind of guard that
# gets subtly wrong. Nothing outside these two sets can be named at all.
_I18N_PAGES = frozenset({"host", "join"})
_I18N_LANGUAGES = frozenset(
    {"es", "pt", "de", "it", "ar", "bn", "zh", "hi", "id", "ja", "ko", "ru", "tr", "vi"}
)


@router.get("/i18n/{page}/{language}", include_in_schema=False)
def interface_dictionary(page: str, language: str):
    """The interface strings for one page in one language.

    English and French are written by hand inside the pages themselves, so they are never
    requested here — they must render with no network involved. These fourteen are
    generated from the English by Amazon Translate and fetched on demand: shipping sixteen
    dictionaries inline would triple two files that are already long, and a reader who
    never leaves English would download fifteen they will not use.

    404 rather than 500 for an unknown pair. A language that has not been generated yet is
    a missing file, not a broken request, and the client falls back to English.
    """
    if page not in _I18N_PAGES or language not in _I18N_LANGUAGES:
        raise HTTPException(status_code=404, detail="Dictionary not found.")

    path = os.path.join(_WEB_DIR, "i18n", f"{page}.{language}.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Dictionary not found.")

    return FileResponse(
        path,
        media_type="application/json",
        # Regenerated only when the English changes, which is a deploy. An hour of caching
        # spares every reader in a non-primary language a request per page load.
        headers={"Cache-Control": "public, max-age=3600"},
    )
