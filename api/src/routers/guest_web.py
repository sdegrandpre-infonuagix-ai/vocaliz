"""Guest web router — serves the browser join page for guests without an account."""
import os

from fastapi import APIRouter
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
