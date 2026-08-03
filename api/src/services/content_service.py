"""Extract plain-text content from a URL or uploaded document."""
import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlparse

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


async def _fetch_url_raw(url: str) -> tuple[str, str]:
    """Fetch a URL once and return (content type, body). Raises HTTPException on failure.

    Extracted so text and metadata come from a single request. Fetching twice would double
    the wait a host sits through and could return two different versions of a page.
    """
    if not re.match(r"^https?://", url):
        raise HTTPException(status_code=400, detail="sourceUrl must start with http:// or https://")

    await _assert_host_is_public(url)

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            response = await client.get(url, headers={"User-Agent": "Salon/0.1"})
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch the URL (HTTP {exc.response.status_code}).",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Could not fetch the URL.") from exc

    return response.headers.get("content-type", ""), response.text


async def fetch_url_content(url: str) -> str:
    """Fetch a URL and return extracted plain text. Raises HTTPException on failure.

    Still returns text alone, so every existing caller is untouched. Callers that also want
    who published it and when use fetch_url_document, which does the same work once.
    """
    content_type, body = await _fetch_url_raw(url)
    if "text/plain" in content_type:
        return body[:_MAX_TEXT_CHARS]
    # HTML by default: plenty of servers mislabel or omit the type, and the parser copes
    # with plain text better than the reverse.
    return _extract_html_text(body)


async def fetch_url_document(url: str) -> tuple[str, dict]:
    """Fetch a URL once and return (text, metadata).

    Separate from fetch_url_content rather than replacing it: the metadata is wanted only
    where a source may be published to the shared corpus, and changing a return type used
    in several places to serve one of them would be the wrong trade.
    """
    content_type, body = await _fetch_url_raw(url)
    if "text/plain" in content_type:
        return body[:_MAX_TEXT_CHARS], {"article_date": "", "author": "", "publisher": ""}
    return _extract_html_text(body), extract_metadata(body, url)


async def _assert_host_is_public(url: str) -> None:
    """Prevent SSRF by rejecting URLs that resolve to private/loopback/link-local IPs.

    Uses a non-blocking DNS lookup via asyncio.to_thread. Note: DNS rebinding is a
    residual risk; use a network-level egress firewall as an additional control.
    """
    host = urlparse(url).hostname
    if not host:
        raise HTTPException(status_code=400, detail="Invalid URL.")
    try:
        ip_str = await asyncio.to_thread(socket.gethostbyname, host)
        ip = ipaddress.ip_address(ip_str)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Could not resolve the URL host.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid URL.")
    if not ip.is_global:
        raise HTTPException(status_code=400, detail="URL not allowed.")


async def extract_file_content(file: UploadFile) -> str:
    """Extract plain text from a .txt or .pdf upload. Raises HTTPException on failure."""
    data = await file.read()
    if len(data) > _MAX_CONTENT_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB).")

    filename = (file.filename or "").lower()
    content_type = file.content_type or ""

    if filename.endswith(".txt") or "text/plain" in content_type:
        return data.decode("utf-8", errors="replace")[:_MAX_TEXT_CHARS]

    if filename.endswith(".pdf") or "pdf" in content_type:
        return _extract_pdf_text(data)

    raise HTTPException(
        status_code=415,
        detail="Unsupported file type. Use .txt or .pdf.",
    )


def parse_article_date(raw: str):
    """A publication date as a datetime, or None.

    Parsed at ingestion rather than stored as the page wrote it. A date kept as a string is
    a date nothing can order, and ordering is the only reason this field exists — "the
    latest news on X" is a question about time. A value that cannot be parsed is therefore
    no value at all, not a string to keep hoping about.

    Only ISO 8601 is accepted, which is what article:published_time and <time datetime>
    are specified to carry. Publishers who write prose dates lose the field, and that is
    better than guessing a day/month order and being wrong half the year.
    """
    from datetime import datetime, timezone

    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        # Python accepts "+00:00" but not the "Z" that most publishers actually emit.
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Naive means the page gave no zone. UTC is the only defensible assumption, and being
    # a few hours out does not change which of two articles is more recent.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def extract_metadata(html: str, url: str = "") -> dict:
    """Who published a page, who wrote it, and when — when the page says so.

    Read from the metadata publishers already emit for social previews and search engines,
    which is far more reliable than guessing from the prose. Every field is optional, and
    absent is the ordinary case: a personal blog names no publisher, and plenty of pages
    carry no date at all.

    The date matters most. "The latest news on X" asks when the article was written, not
    when somebody happened to paste it — ranking on the second is a proxy that goes wrong
    in exactly the case that matters, a host sharing an old piece today.

    Returns article_date, author and publisher. Empty strings for what is missing, matching
    the columns they fill.
    """
    result = {"article_date": "", "author": "", "publisher": ""}
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:  # noqa: BLE001
        return result

    def meta(*candidates) -> str:
        """First matching meta tag, by (attribute, value) pair."""
        for attribute, value in candidates:
            tag = soup.find("meta", attrs={attribute: value})
            if tag is not None:
                content = (tag.get("content") or "").strip()
                if content:
                    return content
        return ""

    # Ordered by how deliberately each is set. article:published_time is written by a
    # publisher for exactly this purpose; a bare "date" is often a build timestamp.
    result["article_date"] = meta(
        ("property", "article:published_time"),
        ("name", "article:published_time"),
        ("property", "og:published_time"),
        ("itemprop", "datePublished"),
        ("name", "publish-date"),
        ("name", "date"),
    )
    if not result["article_date"]:
        # <time datetime="..."> is the element meant for this, and some publishers use it
        # instead of a meta tag.
        time_tag = soup.find("time", attrs={"datetime": True})
        if time_tag is not None:
            result["article_date"] = (time_tag.get("datetime") or "").strip()

    result["author"] = meta(
        ("name", "author"),
        ("property", "article:author"),
        ("itemprop", "author"),
        ("name", "twitter:creator"),
    )

    result["publisher"] = meta(
        ("property", "og:site_name"),
        ("name", "application-name"),
        ("name", "publisher"),
    )
    if not result["publisher"] and url:
        # The host name, as a last resort. It is what a person would say anyway — "I read it
        # on lemonde.fr" — and it is never wrong, only uninformative.
        try:
            host = (urlparse(url).hostname or "").lower()
            result["publisher"] = host.removeprefix("www.")
        except Exception:  # noqa: BLE001
            pass

    # Bounded to the columns that hold them: a page can put anything in a meta tag.
    result["article_date"] = result["article_date"][:40]
    result["author"] = result["author"][:200]
    result["publisher"] = result["publisher"][:200]
    return result


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
            status_code=422, detail="Could not read the PDF."
        ) from exc
