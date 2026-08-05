"""The languages the voice model speaks, as its own documentation lists them.

From docs.x.ai/developers/model-capabilities/audio/speech-to-speech — the page for what this
agent actually runs, checked against the text-to-speech page, which lists the same twenty and
adds `auto`. Seven of the twenty are regional variants: three Arabics, two Portugueses, two
Spanishes. That is the part worth keeping — a caller in Cairo and a caller in Riyadh are
both "Arabic" to a language column and are not the same voice, and pt-BR read to somebody in
Lisbon is noticeably wrong.

Distinct from the seventy interface and caption languages, which come from Amazon Translate
and are about reading. These are about speaking, the list is shorter, and conflating the two
would offer a caller a voice the model cannot produce.

The documentation adds that the model "is also capable of generating speech in additional
languages beyond those listed above, with varying degrees of accuracy" — which is why the
agent's standing instructions tell it to answer in whatever language it hears rather than in
the closest one on this list. This list is what a host may *force*, not the limit of what the
agent may answer.
"""

# Ordered as the documentation orders them, English first because it is the fallback
# everywhere else in the product. `auto` is first of all: it is the default, and it is the
# behaviour every Salon has had until now — follow the speaker.
VOICE_LANGUAGES: list[tuple[str, str]] = [
    ("auto", "Follow the speaker"),
    ("en", "English"),
    ("ar-EG", "العربية (مصر)"),
    ("ar-SA", "العربية (السعودية)"),
    ("ar-AE", "العربية (الإمارات)"),
    ("bn", "বাংলা"),
    ("zh", "中文"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("hi", "हिन्दी"),
    ("id", "Bahasa Indonesia"),
    ("it", "Italiano"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("pt-BR", "Português (Brasil)"),
    ("pt-PT", "Português (Portugal)"),
    ("ru", "Русский"),
    ("es-MX", "Español (México)"),
    ("es-ES", "Español (España)"),
    ("tr", "Türkçe"),
    ("vi", "Tiếng Việt"),
]

# Membership test, built once. The tags are compared exactly, never truncated at the hyphen:
# truncating is what would collapse three Arabics into one and pick a voice from the wrong
# side of a continent.
VOICE_LANGUAGE_TAGS = frozenset(tag for tag, _ in VOICE_LANGUAGES)

# What "no preference" means, and the default for every Salon. Named rather than spelled "auto"
# at each site, because a typo in a string comparison fails silently as "not supported".
FOLLOW_THE_SPEAKER = "auto"


def is_supported(tag: str | None) -> bool:
    """Whether the voice model lists this exact tag.

    Exact, deliberately. `es` is not `es-MX`: the documentation names the variants separately,
    and accepting the base tag would leave the model to choose an accent on the caller's
    behalf — which is the decision the host was trying to make by setting this at all.
    """
    return bool(tag) and tag in VOICE_LANGUAGE_TAGS
