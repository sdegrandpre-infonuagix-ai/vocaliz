"""Condensing a source once, so the agent knows all of it without carrying all of it.

The agent used to receive a document's first 2 500 characters and nothing else. Raising
that limit is not free: a realtime session processes its context on every turn, so a
document carried whole is paid for on every reply, for the whole conversation.

Summarising inverts the trade. One call, before the conversation starts, produces a brief
the agent holds throughout — and the full text stays in the database, searchable, for the
questions a summary cannot answer.
"""
import hashlib
import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"

# Written for a facilitator who will speak from it, which is why it insists on keeping
# names and figures: a summary that drops them leaves the agent unable to answer the
# first concrete question, and the whole point is to avoid that.
_SYSTEM_PROMPT = (
    "You summarise a document for someone who will host a spoken conversation about it. "
    "Keep every concrete claim, name, number and date — they are what participants ask "
    "about. Keep the author's own position distinct from views they report. Write plain "
    "prose, no headings, no bullet points, no preamble. "
    "Write the summary in {language}, whatever language the document is written in: the "
    "conversation will be held in {language}, and a brief the host has to translate in "
    "their head is worse than no brief. Stay under {limit} characters."
)

# The languages xAI documents for its voice models, named rather than left as codes: a
# bare "fr" is understood, but a name leaves nothing to interpret.
#
# Regional variants are kept whole. The voice model distinguishes Brazilian from European
# Portuguese and Mexican from Peninsular Spanish, so a summary that will be read aloud
# beside that voice should match it — truncating pt-BR to pt throws that away.
#
# The documentation adds that the model handles languages beyond this list "with varying
# degrees of accuracy", which is why an unknown code is passed through rather than
# rejected: a summary in an undocumented language beats no summary.
_LANGUAGE_NAMES = {
    "en": "English",
    "ar-EG": "Egyptian Arabic",
    "ar-SA": "Saudi Arabic",
    "ar-AE": "Emirati Arabic",
    "ar": "Arabic",
    "bn": "Bengali",
    "zh": "Simplified Chinese",
    "fr": "French",
    "de": "German",
    "hi": "Hindi",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "pt-BR": "Brazilian Portuguese",
    "pt-PT": "European Portuguese",
    "pt": "Portuguese",
    "ru": "Russian",
    "es-MX": "Mexican Spanish",
    "es-ES": "Peninsular Spanish",
    "es": "Spanish",
    "tr": "Turkish",
    "vi": "Vietnamese",
}


def language_name(code: str | None) -> str:
    """Name a BCP-47 code, keeping the region when it is one we know.

    Falls back from locale to base language to the raw code: "pt-BR" is Brazilian
    Portuguese, "pt-AO" becomes plain Portuguese, "sw" stays "sw" and the model does what
    it can with it.
    """
    if not code:
        return _LANGUAGE_NAMES["en"]
    parts = code.replace("_", "-").split("-")
    locale = f"{parts[0].lower()}-{parts[1].upper()}" if len(parts) > 1 else parts[0].lower()
    base = parts[0].lower()
    return _LANGUAGE_NAMES.get(locale) or _LANGUAGE_NAMES.get(base) or code


def content_hash(text: str) -> str:
    """SHA-256 of the extracted text, for the accounting row."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def summarise(text: str, language: str | None = None) -> tuple[str | None, int | None]:
    """Condense a source into the reader's language. Returns (summary, tokens used).

    `language` is a BCP-47 code — the host's, not the document's. A French host given an
    English article should read a French brief, because the conversation will be French.

    Never raises. A session must open even if the summariser is down, unreachable or
    unconfigured — the agent then falls back to the truncated preview it used before,
    which is worse but still a working conversation.
    """
    if not settings.xai_api_key or not text:
        return None, None

    # Short sources are summarised too, with no shortcut. Passing one through untouched
    # would be correct only if it were already in the host's language, and nothing here
    # knows that: a brief Spanish note handed to a French host would arrive in Spanish.
    # A second and a few hundred tokens is cheaper than that bug.
    #
    # The code is kept whole, region included — see language_name.
    code = language or "en"

    payload = {
        "model": settings.summary_model,
        "messages": [
            {
                "role": "system",
                "content": _SYSTEM_PROMPT.format(
                    limit=settings.summary_target_chars,
                    language=language_name(code),
                ),
            },
            {"role": "user", "content": text},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                _XAI_CHAT_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.xai_api_key}"},
            )
        if resp.status_code != 200:
            logger.warning("Summariser returned %s: %s", resp.status_code, resp.text[:200])
            return None, None
        data = resp.json()
        summary = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage") or {}
        # The provider's own count, not one inferred from characters.
        return summary, usage.get("total_tokens")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Summariser failed: %s", exc)
        return None, None


def search(text: str, query: str, *, max_excerpts: int = 3, window: int = 700) -> list[str]:
    """Find the passages of a source that bear on a question.

    Deliberately not embeddings. The whole document is one string of at most fifty
    thousand characters sitting in a row we already read: scoring its paragraphs by word
    overlap costs microseconds and needs no index, no vector store and no second
    provider. A retrieval pipeline here would be machinery in search of a problem.

    It is a keyword match, so it finds what shares vocabulary with the question and misses
    what is phrased differently — acceptable, because the agent already holds the summary
    and uses this only to recover detail it knows exists.
    """
    if not text or not query:
        return []

    words = {w for w in _normalise(query).split() if len(w) > 3}
    if not words:
        return []

    # Paragraphs, falling back to fixed windows when the text has no blank lines — a PDF
    # extraction often arrives as one unbroken block.
    chunks = [c for c in text.split("\n\n") if c.strip()]
    if len(chunks) < 2:
        chunks = [text[i : i + window] for i in range(0, len(text), window)]

    # A single matching word out of several is noise, not a hit. Matching is by substring
    # so that "sujet" finds "sujets" — useful, but it also lets one incidental word drag
    # in a passage about nothing the participant asked. Requiring two matches once the
    # question offers three or more words filters that out, and returning nothing is a
    # perfectly good answer: the agent still has the summary.
    threshold = 2 if len(words) >= 3 else 1

    scored = []
    for chunk in chunks:
        haystack = _normalise(chunk)
        hits = sum(1 for w in words if w in haystack)
        if hits >= threshold:
            scored.append((hits, chunk.strip()[:window]))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored[:max_excerpts]]


def _normalise(value: str) -> str:
    """Lowercase, and strip the accents that would otherwise split French matches.

    "resistance" must match "résistance": participants speak, transcription varies, and a
    search that fails on an accent would fail constantly in the language most of these
    conversations are held in.
    """
    import unicodedata

    decomposed = unicodedata.normalize("NFD", value.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
