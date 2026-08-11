"""A journal-delivered line is captioned from the line itself, attributed to whoever
actually said it — not from watching the model's own voice, which only ever knows "agent".

`_publish_journal_caption` and `_on_agent_speech` are closures registered deep inside
`entrypoint`, so this is read out of the source the same way test_join_greeting_delay.py
already does for a sibling handler.
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agent as salon  # noqa: E402


def _entrypoint_source() -> str:
    return inspect.getsource(salon.entrypoint)


def _publish_journal_caption_source() -> str:
    source = _entrypoint_source()
    start = source.index("def _publish_journal_caption")
    return source[start : source.index("captions.publish_soon(", start) + 250]


def test_a_tour_is_attributed_to_whoever_actually_said_it():
    block = _publish_journal_caption_source()
    assert 'identity=line.speaker_id if line.kind == "tour" else "agent"' in block


def test_the_caption_is_tagged_with_the_texts_own_language_not_the_listeners():
    """`line.text` is the original utterance, never a translation of it — tagging it with
    `line.language` (what the listener is being spoken to in) would tell the API it is
    already in a language it is not, and the API would skip translating it into whatever
    this room's own reader chose in the caption-language combo box."""
    block = _publish_journal_caption_source()
    assert "language=line.source_language or line.language" in block


def test_the_generic_caption_is_skipped_for_a_journal_rendition():
    """`_publish_journal_caption` already captions this turn, correctly attributed — the
    generic handler must not caption it a second time under "agent"."""
    source = _entrypoint_source()
    start = source.index('@agent_session.on("conversation_item_added")')
    block = source[start : source.index("\n\n", start)]
    assert 'pending_journal_caption["active"]' in block
    assert "if not journal_rendition:" in block
    # The skip has to guard the publish call, not just exist somewhere in the handler.
    assert block.index("if not journal_rendition:") < block.index("captions.publish_soon(")


def test_the_flag_is_set_before_the_model_is_asked_to_speak():
    """Session_voice's `conversation_item_added` fires synchronously inside `generate_reply`,
    so the flag has to be set before that call, not after — see `SessionVoice.on_before_speak`."""
    source = _entrypoint_source()
    start = source.index("def _mark_journal_speaking")
    block = source[start : source.index("\n\n", start)]
    assert 'pending_journal_caption["active"] = True' in block


def test_the_journal_voice_and_follow_call_are_both_wired_to_the_new_hooks():
    source = _entrypoint_source()
    start = source.index("following_task = asyncio.create_task(")
    block = source[start : source.index("stop=stop_following", start)]
    assert "on_before_speak=_mark_journal_speaking" in block
    assert "on_delivered=_publish_journal_caption" in block
