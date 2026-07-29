"""Extract plain-text content from a URL or uploaded document."""
import re

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException, UploadFile

_ALLOWED_MIME_TYPES = {
    "text/plain",
    "application/pdf",
    "application/x-pdf",
}
_MAX_CONTENT_BYTES = 5 * 1024 * 1024  # 5 MB
_MAX_TEXT_CHARS = 50_000              # trim after extraction to keep context manageable


async def fetch_url_content(url: str) -> str:
    """Fetch a URL and return extracted plain text. Raises HTTPException on failure."""
    if not re.match(r"^https?://", url):
        raise HTTPException(status_code=400, detail="sourceUrl doit commencer par http:// ou https://")
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            response = await client.get(url, headers={"User-Agent": "Salon/0.1"})
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Impossible de récupérer l'URL (HTTP {exc.response.status_code}).",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Impossible de récupérer l'URL.") from exc

    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type or "application/xhtml" in content_type:
        return _extract_html_text(response.text)
    if "text/plain" in content_type:
        return response.text[:_MAX_TEXT_CHARS]
    # Default: try HTML parsing
    return _extract_html_text(response.text)


async def extract_file_content(file: UploadFile) -> str:
    """Extract plain text from a .txt or .pdf upload. Raises HTTPException on failure."""
    data = await file.read()
    if len(data) > _MAX_CONTENT_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 5 Mo).")

    filename = (file.filename or "").lower()
    content_type = file.content_type or ""

    if filename.endswith(".txt") or "text/plain" in content_type:
        return data.decode("utf-8", errors="replace")[:_MAX_TEXT_CHARS]

    if filename.endswith(".pdf") or "pdf" in content_type:
        return _extract_pdf_text(data)

    raise HTTPException(
        status_code=415,
        detail="Type de fichier non supporté. Utilisez .txt ou .pdf.",
    )


def _extract_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style/nav elements that are not content
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)[:_MAX_TEXT_CHARS]


def _extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)[:_MAX_TEXT_CHARS]
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail="Impossible de lire le PDF."
        ) from exc
