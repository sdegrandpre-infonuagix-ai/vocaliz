"""The Interpreter port and its adapters.

`port` is what the orchestrator imports. Everything else in here implements it, and the
orchestrator never names any of them — see `test_interprete_port.py`, which fails the build
if a provider SDK ever appears under `src/`.
"""
from src.interprete.base import InterpreteBase, LanguageModel, SpeechToText, TextToSpeech
from src.interprete.fake import InterpreteFake
from src.interprete.languages import base_language, offered_languages
from src.interprete.port import (
    Annonce,
    FallbackVoice,
    Interprete,
    InterpreteError,
    Participant,
    ProviderUnavailable,
    RealtimeSession,
    Tour,
    UnsupportedLanguage,
    Utterance,
    notice_for,
)
from src.interprete.s2s import InterpreteS2S

__all__ = [
    "Annonce",
    "FallbackVoice",
    "Interprete",
    "InterpreteError",
    "InterpreteBase",
    "InterpreteFake",
    "InterpreteS2S",
    "Participant",
    "ProviderUnavailable",
    "RealtimeSession",
    "LanguageModel",
    "SpeechToText",
    "TextToSpeech",
    "Tour",
    "UnsupportedLanguage",
    "Utterance",
    "base_language",
    "notice_for",
    "offered_languages",
]
