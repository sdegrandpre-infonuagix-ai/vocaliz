"""Rendering one turn of speech into another language, once.

Amazon Translate rather than the model already in the stack: it answers in a couple of
hundred milliseconds where a chat completion takes seconds, and captions that arrive
after the next person has started talking are worse than no captions. It also costs about
fifteen US dollars per million characters, which against realtime voice is noise.

Every translation is cached on (utterance, language). The cache is what makes a second
viewer in the same language free, and a ten-minute salon is a few hundred turns.
"""
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session as DbSession

from src.config import settings
from src.models.utterance import Utterance, UtteranceTranslation

logger = logging.getLogger(__name__)

_client = None

# Amazon Translate takes ISO 639-1, not BCP-47: "en-US" is rejected where "en" is
# accepted. These are the regional codes it does distinguish, and they are worth keeping
# because the difference is audible — Quebec French is not France French.
_REGIONAL = {"fr-ca", "pt-pt", "pt-br", "zh-tw", "zh-cn", "es-mx", "en-gb", "nb-no"}


def _translate_client():
    """Created lazily and reused: a boto3 client costs about a second to build, and a
    cold Lambda that builds one per turn would spend that second on the caption path."""
    global _client
    if _client is None:
        _client = boto3.client("translate", region_name=settings.aws_region)
    return _client


def normalise(code: str | None) -> str | None:
    """A BCP-47 tag as Amazon Translate wants it.

    Regional variants it knows are kept; every other region is dropped rather than passed
    through, since "en-CA" would be refused outright while "en" answers.
    """
    if not code:
        return None
    tag = code.strip().lower().replace("_", "-")
    if not tag:
        return None
    if tag in _REGIONAL:
        return tag
    return tag.split("-")[0] or None


def same_language(a: str | None, b: str | None) -> bool:
    """Whether translating from a to b would be a no-op.

    Compared on the primary subtag: someone reading captions in "fr" does not need a turn
    spoken in "fr-CA" translated, and paying to turn French into French would also risk
    the translator quietly rephrasing it.
    """
    if not a or not b:
        return False
    return a.strip().lower().split("-")[0] == b.strip().lower().split("-")[0]


def translate(text: str, target: str, source: str | None = None) -> str | None:
    """One call to Amazon Translate. None when it fails.

    Best-effort by design: a caption that cannot be translated is shown in its original
    language, which is a degraded conversation rather than a broken one.
    """
    target_code = normalise(target)
    if not target_code or not text.strip():
        return None
    try:
        response = _translate_client().translate_text(
            Text=text,
            # "auto" rather than the model's guess when it did not report one. Translate
            # detects the source itself and is right more often than a missing value.
            SourceLanguageCode=normalise(source) or "auto",
            TargetLanguageCode=target_code,
        )
        return response["TranslatedText"]
    except (BotoCoreError, ClientError):
        logger.warning("Translation into %s failed", target_code, exc_info=True)
        return None


def translated_text(db: DbSession, utterance: Utterance, target: str) -> str:
    """This turn in the requested language, from cache when it is there.

    Falls back to the spoken text on every failure path — an untranslated caption is
    still a caption. Returns the spoken text unchanged when the turn is already in the
    requested language.
    """
    if same_language(utterance.language, target):
        return utterance.text

    language = normalise(target)
    if not language:
        return utterance.text

    cached = db.get(UtteranceTranslation, (utterance.id, language))
    if cached is not None:
        return cached.text

    rendered = translate(utterance.text, language, utterance.language)
    if rendered is None:
        return utterance.text

    try:
        db.add(
            UtteranceTranslation(
                utterance_id=utterance.id, language=language, text=rendered
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001
        # A race with another viewer asking for the same language at the same moment.
        # Both hold the same text, so losing the insert costs one redundant call and
        # nothing else — never the caption.
        db.rollback()
        logger.debug("Could not cache translation into %s", language, exc_info=True)

    return rendered
