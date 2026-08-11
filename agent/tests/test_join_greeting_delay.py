"""A guest's audio pipeline needs a moment to catch up to the token their browser was
already handed — reported live as arriving mid-sentence, the greeting already under way
before playback was ready to render it.

`_follow_the_journal` is a closure registered deep inside `entrypoint`, so this is read out
of the source the same way test_privacy_toggle.py already does for its sibling handler.
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agent as salon  # noqa: E402


def _entrypoint_source() -> str:
    return inspect.getsource(salon.entrypoint)


def test_the_greeting_waits_for_the_guests_audio_to_catch_up():
    source = _entrypoint_source()
    start = source.index("salon_agent.set_journal_link(link)")
    block = source[start : source.index("_journal_intro_instructions", start)]
    assert "await asyncio.sleep(1)" in block
