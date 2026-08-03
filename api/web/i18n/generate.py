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
import subprocess
import sys

import boto3

HERE = pathlib.Path(__file__).parent
WEB = HERE.parent
OVERRIDES = HERE / "overrides"

# The languages the live captions offer, minus the two written by hand. Kept in step with
# CAPTION_LANGS in the pages and CAPTION_LANGUAGES in the mobile app — a language offered
# for captions but missing here would show an English interface beside translated speech.
TARGETS = [
    "es", "pt", "de", "it", "ar", "bn", "zh", "hi", "id", "ja", "ko", "ru", "tr", "vi",
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


def translate_all(strings: dict, language: str, client) -> dict:
    """Every string in one language, one call each.

    Placeholders such as {email} are left alone by Amazon Translate in practice, but they
    are checked afterwards rather than trusted: a lost placeholder produces a sentence
    with a hole in it, which is worse than an untranslated one.
    """
    out = {}
    for key, text in strings.items():
        try:
            response = client.translate_text(
                Text=text, SourceLanguageCode="en", TargetLanguageCode=language
            )
            rendered = response["TranslatedText"]
        except Exception as exc:  # noqa: BLE001
            print(f"    {key}: failed ({exc}), keeping English")
            out[key] = text
            continue

        # Every {placeholder} present in the English must survive. Falling back to
        # English is the lesser failure: a reader sees the wrong language, not a
        # sentence missing the name it was about.
        placeholders = {p for p in text.split("{")[1:]}
        expected = {p.split("}")[0] for p in placeholders if "}" in p}
        if any("{" + p + "}" not in rendered for p in expected):
            print(f"    {key}: placeholder lost, keeping English")
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
