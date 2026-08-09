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
