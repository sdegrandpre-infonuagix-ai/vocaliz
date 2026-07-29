"""Guest web router — serves the browser join page for anonymous participants."""
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
