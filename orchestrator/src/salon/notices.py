"""What the system says to one participant, in that participant's language.

Written out per language rather than translated on demand, and for the same reason the
breakdown notice in `interprete/port.py` is: these are said at moments when the thing that
would translate them is either broken or deliberately not being used. A handful of short
sentences is also the kind of copy that ought to be read by somebody who speaks the
language, which a runtime translation never is.

English when the language is not one of these. A notice in the wrong language still tells
somebody that something happened; silence tells them nothing.
"""
from __future__ import annotations

MICROPHONE_CUT = {
    "fr": "L'hôte a coupé votre micro. Vous entendez toujours la conversation.",
    "en": "The host has muted your microphone. You can still hear the conversation.",
    "es": "El anfitrión ha silenciado tu micrófono. Sigues oyendo la conversación.",
    "de": "Der Gastgeber hat Ihr Mikrofon stummgeschaltet. Sie hören das Gespräch weiterhin.",
    "pt": "O anfitrião silenciou o seu microfone. Continua a ouvir a conversa.",
    "it": "L'ospite ha disattivato il tuo microfono. Continui a sentire la conversazione.",
}

MICROPHONE_RESTORED = {
    "fr": "Votre micro est rétabli. Vous pouvez reprendre la parole.",
    "en": "Your microphone is back on. You can speak again.",
    "es": "Tu micrófono está activo de nuevo. Puedes volver a hablar.",
    "de": "Ihr Mikrofon ist wieder an. Sie können wieder sprechen.",
    "pt": "O seu microfone está ligado outra vez. Pode voltar a falar.",
    "it": "Il tuo microfono è di nuovo attivo. Puoi tornare a parlare.",
}


def _in(table: dict[str, str], language: str) -> str:
    return table.get(language.split("-")[0].lower(), table["en"])


def microphone_cut(language: str) -> str:
    """Told to somebody whose microphone the host has just closed.

    It says they can still hear, because that is the part they cannot verify for
    themselves: silence from a microphone is indistinguishable from a broken interpreter,
    and the person it happened to is the least able to tell which.
    """
    return _in(MICROPHONE_CUT, language)


def microphone_restored(language: str) -> str:
    """Told when it opens again.

    Somebody who has been silent for a minute needs to know before they try, or the first
    thing they say is spent testing whether anyone can hear them.
    """
    return _in(MICROPHONE_RESTORED, language)


# ── Introducing people (Story 6.9) ────────────────────────────────────────────
#
# The topology removes the two things that normally say who is talking: nobody hears
# anybody's real voice, and everything arrives in the listener's own language. Without an
# introduction a Salon is a series of sentences from nowhere.

# Language names, in the language of whoever is being told. A matrix rather than a list
# because "Marie speaks French" has to be said in German to Hans and in Welsh to Rhys.
# Unknown pairs fall back to the BCP-47 code, which is wrong but legible — and it is the
# code the adapters themselves use, so it is at least traceable.
LANGUAGE_NAMES: dict[str, dict[str, str]] = {
    "fr": {"fr": "français", "en": "anglais", "es": "espagnol", "de": "allemand",
           "pt": "portugais", "it": "italien", "cy": "gallois"},
    "en": {"fr": "French", "en": "English", "es": "Spanish", "de": "German",
           "pt": "Portuguese", "it": "Italian", "cy": "Welsh"},
    "es": {"fr": "francés", "en": "inglés", "es": "español", "de": "alemán",
           "pt": "portugués", "it": "italiano", "cy": "galés"},
    "de": {"fr": "Französisch", "en": "Englisch", "es": "Spanisch", "de": "Deutsch",
           "pt": "Portugiesisch", "it": "Italienisch", "cy": "Walisisch"},
    "pt": {"fr": "francês", "en": "inglês", "es": "espanhol", "de": "alemão",
           "pt": "português", "it": "italiano", "cy": "galês"},
    "it": {"fr": "francese", "en": "inglese", "es": "spagnolo", "de": "tedesco",
           "pt": "portoghese", "it": "italiano", "cy": "gallese"},
    "cy": {"fr": "Ffrangeg", "en": "Saesneg", "es": "Sbaeneg", "de": "Almaeneg",
           "pt": "Portiwgaleg", "it": "Eidaleg", "cy": "Cymraeg"},
}

# What somebody is called when nobody gave them a name. Never their telephone number or
# their address: that is how they reached the Salon, not who they are, and the others have
# no business being told it.
SOMEBODY = {
    "fr": "Quelqu'un d'autre",
    "en": "Someone else",
    "es": "Otra persona",
    "de": "Jemand anderes",
    "pt": "Outra pessoa",
    "it": "Un'altra persona",
    "cy": "Rhywun arall",
}

_INTRODUCES = {
    "fr": "{name} parle {language}.",
    "en": "{name} speaks {language}.",
    "es": "{name} habla {language}.",
    "de": "{name} spricht {language}.",
    "pt": "{name} fala {language}.",
    "it": "{name} parla {language}.",
    "cy": "Mae {name} yn siarad {language}.",
}

_ALREADY_HERE = {
    "fr": "Déjà là : {people}.",
    "en": "Already here: {people}.",
    "es": "Ya están aquí: {people}.",
    "de": "Schon da: {people}.",
    "pt": "Já aqui: {people}.",
    "it": "Già qui: {people}.",
    "cy": "Yma'n barod: {people}.",
}

_ALL_ONE_LANGUAGE = {
    "fr": "Tout le monde ici parle {language}.",
    "en": "Everyone here speaks {language}.",
    "es": "Aquí todos hablan {language}.",
    "de": "Hier sprechen alle {language}.",
    "pt": "Aqui toda a gente fala {language}.",
    "it": "Qui parlano tutti {language}.",
    "cy": "Mae pawb yma'n siarad {language}.",
}


def _base(language: str) -> str:
    return language.split("-")[0].lower()


def language_name(spoken: str, *, told_in: str) -> str:
    """What `spoken` is called in `told_in`.

    Two fallbacks, and they point in the same direction as the sentence templates: a
    listener whose language nobody has translated into hears English, not a bare code. Only
    a *spoken* language nobody has named falls back to its BCP-47 code — wrong but legible,
    and it is the code the adapters themselves use, so it is at least traceable.
    """
    return LANGUAGE_NAMES.get(_base(told_in), LANGUAGE_NAMES["en"]).get(_base(spoken), spoken)


def display_name(name: str | None, *, told_in: str) -> str:
    """What to call somebody out loud.

    A neutral designation when nobody supplied a name — which is the ordinary case for a
    telephone participant, and precisely the case where the obvious fallback would be to
    read out their number.
    """
    return name.strip() if name and name.strip() else _in(SOMEBODY, told_in)


def introduces(name: str | None, spoken: str, *, told_in: str) -> str:
    """One person and the language they were heard in, said to one listener.

    A neutral designation when there is no name — the ordinary case for a telephone
    participant, and precisely the case where the obvious fallback would be to read out
    their number.
    """
    return _in(_INTRODUCES, told_in).format(
        name=display_name(name, told_in=told_in),
        language=language_name(spoken, told_in=told_in),
    )


def already_here(people, *, told_in: str) -> str | None:
    """Who has already spoken, said to somebody who has just arrived.

    `people` is a sequence of (name, language) pairs, name possibly None.

    None when there is nobody to name: an arrival into a Salon where nothing has been said
    is told nothing, because there is nothing to say and no language to invent.

    When everybody already heard shares one language, that is said once rather than spelled
    out per person — naming each person's language when it is everybody's is several
    sentences carrying one bit between them.
    """
    people = list(people)
    if not people:
        return None

    # "Everyone here speaks French" is only worth saying to somebody who speaks it too. To
    # anybody else it withholds the one thing they needed — who is here — and replaces it
    # with a fact about a language they do not share.
    spoken = {_base(language) for _, language in people}
    if spoken == {_base(told_in)}:
        return _in(_ALL_ONE_LANGUAGE, told_in).format(
            language=language_name(people[0][1], told_in=told_in)
        )

    return _in(_ALREADY_HERE, told_in).format(
        people="; ".join(
            introduces(name, language, told_in=told_in).rstrip(".")
            for name, language in people
        )
    )


# ── Giving a late arrival the history (Story 6.10) ────────────────────────────

_HISTORY_SHARED = {
    "fr": "{name} vient d'arriver et va entendre ce qui s'est dit avant.",
    "en": "{name} has just joined and will hear what was said earlier.",
    "es": "{name} acaba de llegar y oirá lo que se dijo antes.",
    "de": "{name} ist gerade dazugekommen und hört, was vorher gesagt wurde.",
    "pt": "{name} acabou de entrar e vai ouvir o que foi dito antes.",
    "it": "{name} è appena arrivato e sentirà quanto è stato detto prima.",
    "cy": "Mae {name} newydd gyrraedd a bydd yn clywed yr hyn a ddywedwyd yn gynharach.",
}


def history_shared_with(name: str | None, *, told_in: str) -> str:
    """Told to everybody already here when an arrival is given the history.

    What they said before this person existed to them is about to be said to that person.
    Nobody should find that out afterwards, and there is no way to take it back — so the
    only honest moment to say it is now.
    """
    return _in(_HISTORY_SHARED, told_in).format(name=display_name(name, told_in=told_in))


# ── A participant on the telephone (Story 6.13 / FR57) ────────────────────────

_ON_THE_TELEPHONE = {
    "fr": "{name} participe par téléphone : ni caméra, ni écran.",
    "en": "{name} is on the telephone: no camera and no screen.",
    "es": "{name} participa por teléfono: sin cámara ni pantalla.",
    "de": "{name} ist per Telefon dabei: keine Kamera und kein Bildschirm.",
    "pt": "{name} participa por telefone: sem câmara nem ecrã.",
    "it": "{name} partecipa per telefono: niente telecamera né schermo.",
    "cy": "Mae {name} ar y ffôn: dim camera na sgrin.",
}


def on_the_telephone(name: str | None, *, told_in: str) -> str:
    """Said when somebody joins by telephone.

    Without it their empty tile reads as a person who chose not to be seen — a different
    thing, and one that invites a judgement they have not earned.
    """
    return _in(_ON_THE_TELEPHONE, told_in).format(name=display_name(name, told_in=told_in))


# ── A backlog said in substance (Story 7.2 / FR53) ────────────────────────────

# Two tables rather than one with a plural rule. Six languages disagree about how plurals
# work, and a sentence built by gluing a number onto a stem is exactly the kind of copy that
# reads as machine-written in every one of them.
_CONDENSED_ONE = {
    "fr": "Pendant que vous écoutiez, une personne a parlé. Voici l'essentiel.",
    "en": "While you were listening, someone else spoke. Here is the gist.",
    "es": "Mientras escuchabas, habló otra persona. Esto es lo esencial.",
    "de": "Während Sie zugehört haben, hat jemand gesprochen. Hier das Wesentliche.",
    "pt": "Enquanto ouvia, outra pessoa falou. Aqui está o essencial.",
    "it": "Mentre ascoltavi, ha parlato un'altra persona. Ecco l'essenziale.",
}

_CONDENSED_MANY = {
    "fr": "Pendant que vous écoutiez, {count} personnes ont parlé. Voici l'essentiel.",
    "en": "While you were listening, {count} people spoke. Here is the gist.",
    "es": "Mientras escuchabas, hablaron {count} personas. Esto es lo esencial.",
    "de": "Während Sie zugehört haben, haben {count} Personen gesprochen. Hier das Wesentliche.",
    "pt": "Enquanto ouvia, falaram {count} pessoas. Aqui está o essencial.",
    "it": "Mentre ascoltavi, hanno parlato {count} persone. Ecco l'essenziale.",
}


def condensed_while_listening(count: int, *, told_in: str) -> str:
    """Said just before a summary, naming how many people it covers.

    Without it a summary is indistinguishable from the conversation having been quiet: the
    listener hears less than everybody else and has no way of knowing it happened. The count
    is of people rather than of messages, because that is what tells them how much of the
    room they are getting the gist of — somebody who spoke four times is one person to catch
    up on, not four.
    """
    if count <= 1:
        return _in(_CONDENSED_ONE, told_in)
    return _in(_CONDENSED_MANY, told_in).format(count=count)


# ── A room that cannot keep up (Story 7.3 / FR55) ─────────────────────────────

# "Vocaliz is busy" is the product saying its own name, and it stays in English in every one
# of these. Translating a brand gives somebody six different things to search for when they
# want to report the problem, and gives support six things to recognise. The rest of the
# sentence is theirs — three English words on their own tell a German reader nothing.
_VOCALIZ_IS_BUSY = {
    "fr": "Vocaliz is busy : la conversation va plus vite que votre interprète. "
    "Attendez un instant avant de reprendre la parole.",
    "en": "Vocaliz is busy: the conversation is running ahead of your interpreter. "
    "Give it a moment before speaking again.",
    "es": "Vocaliz is busy: la conversación va más rápido que tu intérprete. "
    "Espera un momento antes de volver a hablar.",
    "de": "Vocaliz is busy: Das Gespräch läuft Ihrem Dolmetscher davon. "
    "Warten Sie einen Moment, bevor Sie weitersprechen.",
    "pt": "Vocaliz is busy: a conversa está a andar mais depressa do que o seu intérprete. "
    "Espere um momento antes de voltar a falar.",
    "it": "Vocaliz is busy: la conversazione corre più veloce del tuo interprete. "
    "Aspetta un momento prima di riprendere a parlare.",
}


def vocaliz_is_busy(*, told_in: str) -> str:
    """Said to one participant when their own room has fallen too far behind.

    Never to the Salon. One interpreter's lag says nothing about anybody else's, and warning
    a room that is keeping up perfectly well would be telling it something untrue about
    itself.
    """
    return _in(_VOCALIZ_IS_BUSY, told_in)
