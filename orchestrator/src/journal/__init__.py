"""A Salon's journal, the reading position of each of its interpreters, and its translations.

`SalonLog` is what an orchestrator instance holds one of per Salon. The three pieces below
it are separable on purpose: the journal is what was said and never changes, the cursors are
the only thing that moves, and the translations are a cache keyed on a pair that several
readers share.
"""
from src.journal.cleaning import (
    MAX_PAUSE_MS,
    SIGNIFICANT_PAUSE_MS,
    clean,
    neutralise,
    pause_marker,
    pause_seconds,
    spoken_length,
    without_markers,
)
from src.journal.cursors import Cursors
from src.journal.journal import (
    CHARACTERS_PER_SECOND,
    arrival_key,
    Journal,
    JournalEntry,
    arrival_key,
    content_seconds,
)
from src.journal.salon_log import SalonLog
from src.journal.splitting import MAX_MESSAGE_CHARACTERS, split_intervention
from src.journal.sql_store import SqlJournalStore
from src.journal.store import InMemoryJournalStore, JournalStore, SalonState
from src.journal.translations import Translate, Translations

__all__ = [
    "arrival_key",
    "CHARACTERS_PER_SECOND",
    "Cursors",
    "MAX_PAUSE_MS",
    "SIGNIFICANT_PAUSE_MS",
    "InMemoryJournalStore",
    "Journal",
    "MAX_MESSAGE_CHARACTERS",
    "JournalEntry",
    "JournalStore",
    "SalonLog",
    "SalonState",
    "SqlJournalStore",
    "arrival_key",
    "Translate",
    "Translations",
    "clean",
    "content_seconds",
    "neutralise",
    "pause_marker",
    "pause_seconds",
    "spoken_length",
    "without_markers",
    "split_intervention",
]
