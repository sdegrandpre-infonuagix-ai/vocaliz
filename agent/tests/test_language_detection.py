"""Tests for Story 2.8 — Automatic Language Detection and Multilingual Expression."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agent as salon  # noqa: E402


# ─── Instructions contain language detection behaviour ────────────────────────

def test_base_instructions_mention_language_detection():
    assert "LANGUAGE DETECTION" in salon._BASE_INSTRUCTIONS


def test_base_instructions_no_manual_selection():
    assert "no configuration required" in salon._BASE_INSTRUCTIONS


def test_base_instructions_respond_in_participant_language():
    instructions = salon._BASE_INSTRUCTIONS
    assert "language they are using" in instructions


def test_base_instructions_detect_without_asking():
    assert "Never ask participants to configure or select a language" in salon._BASE_INSTRUCTIONS


def test_base_instructions_persist_language_throughout_session():
    assert "entire session" in salon._BASE_INSTRUCTIONS


def test_base_instructions_multilingual_participants():
    assert "different languages" in salon._BASE_INSTRUCTIONS


def test_base_instructions_french_example():
    assert "French" in salon._BASE_INSTRUCTIONS or "french" in salon._BASE_INSTRUCTIONS.lower()


def test_base_instructions_english_example():
    assert "English" in salon._BASE_INSTRUCTIONS or "english" in salon._BASE_INSTRUCTIONS.lower()
