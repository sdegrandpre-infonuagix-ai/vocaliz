"""Generate the non-primary interface languages from the English one.

English and French are written by hand, inline in host.html and join.html. They are the
two languages the product is built in, they must be exact, and they must render with no
network involved. The other fourteen — the ones the live captions already support — are
machine-translated from the English by Amazon Translate and committed as JSON.

Generated rather than hand-written for one reason: a hand-written sixteen-language
dictionary drifts. A string changes in English, nobody remembers the other fifteen, and
the interface quietly shows a mixture. Re-running this is the whole maintenance story.

The English source is read out of the HTML itself, so the pages stay the single source of
truth and nothing has to be kept in step by hand. Node evaluates the literal, because it
contains string concatenation that no JSON parser would accept.

Hand corrections survive. Anything in overrides/<lang>.json wins over the machine output,
so a bad rendering can be fixed once and stay fixed.

    python api/web/i18n/generate.py            # every language
    python api/web/i18n/generate.py es pt      # only these
"""
import json
import pathlib
import re
import subprocess
import sys

import boto3

HERE = pathlib.Path(__file__).parent
WEB = HERE.parent
OVERRIDES = HERE / "overrides"

# The interface languages, minus the two written by hand. Must stay in step with CAPTION_LANGS
# in the pages and CAPTION_LANGUAGES in the mobile app: every language the site offers has a
# dictionary, with no exceptions. A caption language missing from here would show an English
# interface beside translated speech — offered in a language the interface does not speak.
TARGETS = [
    "es", "pt", "de", "it", "ar", "fa", "bn", "zh", "hi", "id", "ja", "ko", "ru", "tr", "vi",
]

PAGES = ["host", "join"]


def extract_english(page: str) -> dict:
    """The English dictionary, as the page itself defines it.

    Evaluated by Node rather than parsed: the literal uses `'a ' + 'b'` concatenation to
    keep long strings readable, which is valid JavaScript and invalid JSON.
    """
    source = (WEB / f"{page}.html").read_text(encoding="utf-8")
    start = source.index("{", source.index("I18N = {"))
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                literal = source[start : i + 1]
                break
    else:
        raise SystemExit(f"{page}.html: could not find the end of the I18N literal")

    result = subprocess.run(
        ["node", "-e", f"process.stdout.write(JSON.stringify(({literal}).en))"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise SystemExit(f"{page}.html: Node could not evaluate the dictionary\n{result.stderr}")
    return json.loads(result.stdout)


# Words Amazon Translate must not touch, longest first so a plural is not eaten by its
# singular. "Salon" is the one that matters: left alone it became "salão de beleza" in
# Portuguese and the beauty-salon word in Hindi, Bengali and Vietnamese — the product renamed
# as a hairdresser in four languages. The brand is protected too, because Arabic, Japanese and
# Korean otherwise transliterate it while the wordmark on the page stays in Latin letters.
PRODUCT_WORDS = [("Salons", "XVSALONPLX"), ("Salon", "XVSALONSGX"), ("Vocaliz", "XVBRANDX")]


def _placeholders(text: str) -> list[str]:
    return re.findall(r"\{[a-zA-Z]+\}", text)


def _protect(text: str, words: list[tuple[str, str]]) -> str:
    """Words and {placeholders} swapped for opaque tokens before translation.

    Placeholders used to be passed through as-is and merely checked afterwards, which was fine
    for the left-to-right languages and failed for Farsi: four strings came back with the
    braces reordered or dropped, and the check could only fall back to English. A token that
    looks like a word survives where punctuation does not.
    """
    for word, token in words:
        text = text.replace(word, token)
    for i, ph in enumerate(dict.fromkeys(_placeholders(text))):
        text = text.replace(ph, f"XPH{i}X")
    return text


def _restore(text: str, original: str, words: list[tuple[str, str]]) -> str:
    for i, ph in enumerate(dict.fromkeys(_placeholders(original))):
        text = text.replace(f"XPH{i}X", ph)
    for word, token in words:
        text = text.replace(token, word)
    return text


def _intact(rendered: str, english: str, words: list[tuple[str, str]]) -> bool:
    """Everything held back must come back exactly as often as it went in.

    Counted rather than merely looked for: Bengali once transliterated two tokens of three and
    left the last one, so "is it in there" passed on a sentence reading "XVBRANDX XVSALONPLX".
    """
    if any(rendered.count(p) != english.count(p) for p in set(_placeholders(english))):
        return False
    return all(rendered.count(w) == english.count(w) for w, _ in words)


def translate_all(strings: dict, language: str, client) -> dict:
    """Every string in one language, one call each."""
    out = {}
    for key, text in strings.items():
        rendered = None
        # Protecting the brand is better when it works, but three opaque tokens in one short
        # sentence is more than some languages tolerate. So a failure retries with the brand
        # left translatable, which keeps the defect that actually matters — the product noun —
        # fixed even where the nicety cannot be.
        for words in (PRODUCT_WORDS, [w for w in PRODUCT_WORDS if w[0] != "Vocaliz"]):
            try:
                response = client.translate_text(
                    Text=_protect(text, words),
                    SourceLanguageCode="en",
                    TargetLanguageCode=language,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"    {key}: failed ({exc}), keeping English")
                break
            candidate = _restore(response["TranslatedText"], text, words)
            if _intact(candidate, text, words):
                rendered = candidate
                break

        # Falling back to English is the lesser failure: a reader sees the wrong language, not
        # a sentence missing the name it was about.
        if rendered is None:
            print(f"    {key}: protected text lost, keeping English")
            out[key] = text
            continue

        out[key] = rendered
    return out


def main(argv: list[str]) -> None:
    languages = argv or TARGETS
    unknown = [lang for lang in languages if lang not in TARGETS]
    if unknown:
        raise SystemExit(f"Not a generated language: {', '.join(unknown)}")

    client = boto3.client("translate")

    for page in PAGES:
        english = extract_english(page)
        print(f"{page}.html: {len(english)} strings")

        for language in languages:
            print(f"  {language}")
            translated = translate_all(english, language, client)

            override_path = OVERRIDES / f"{page}.{language}.json"
            if override_path.exists():
                corrections = json.loads(override_path.read_text(encoding="utf-8"))
                translated.update(corrections)
                print(f"    {len(corrections)} hand corrections applied")

            target = HERE / f"{page}.{language}.json"
            target.write_text(
                json.dumps(translated, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )


if __name__ == "__main__":
    main(sys.argv[1:])
