"""Writing instead of speaking, and whose words the agent will say.

Two different things share one path and must not be confused. The host's typed line is spoken
aloud word for word, in the agent's voice — they are borrowing it. A guest's typed line is put
to the agent as something said to it, which is what their speaking would have done.

The distinction is a permission, not a preference. Anyone who reaches the verbatim branch can
put words in the agent's mouth, and the room has no way to tell those words from the agent's
own — a participant hears one voice and no attribution.

Read out of the entrypoint's source. It needs a LiveKit room, a realtime model and a live API
before it does anything, and these facts are worth pinning where the wiring cannot be run.
"""
import inspect

import agent as salon


def _handler() -> str:
    source = inspect.getsource(salon.entrypoint)
    start = source.index('msg.get("action") == "text_message"')
    return source[start : source.index("ctx.room.on(\"data_received\"", start)]


def _code(block: str) -> str:
    """The same block with its comments removed.

    The comments here explain what the code deliberately does *not* do — "a say() here would be
    captioned as speech nobody heard" — so a test asserting the absence of `say(` reads its own
    explanation and fails. Prose is not evidence about behaviour either way.
    """
    return "\n".join(
        line for line in block.splitlines() if not line.lstrip().startswith("#")
    )


# ─── Who may lend the agent its voice ─────────────────────────────────────────

def test_only_the_host_is_relayed_in_their_own_words():
    handler = _handler()
    assert "sender == host_identity" in handler
    assert "generate_reply" in handler[handler.index("if speaks_aloud:") :]


def test_the_relay_is_translated_rather_than_read_out_literally():
    """say() is text-to-speech and would deliver a French sentence to somebody who speaks only
    Japanese — which is the whole scenario this exists for. Word for word in substance, in the
    listener's language."""
    spoken = _code(_handler())
    spoken = spoken[spoken.index("if speaks_aloud:") :]
    assert "agent_session.say(" not in spoken
    assert "each listener's own language" in _handler()


def test_the_relay_adds_nothing_of_its_own():
    """"He would like me to tell you" defeats the point: the host is lending the voice, not
    briefing an intermediary."""
    handler = _handler()
    assert "Add no greeting, no comment, no preamble" in handler
    assert "never say that somebody asked you to pass it on" in handler


def test_the_host_is_named_by_the_api_not_inferred_from_the_identity():
    """The old rule — anything not prefixed "guest-" is the host — stopped being true when a
    registered guest began joining under their own account id. Inferring it here would hand
    the agent's voice to every guest with an account."""
    source = inspect.getsource(salon.entrypoint)
    assert 'detail.get("hostIdentity")' in source
    assert 'startswith("guest-")' not in _handler()


def test_an_unknown_host_lends_its_voice_to_nobody():
    """host_identity is empty until the API answers. Empty must mean nobody rather than
    everybody, or an unreachable API ends with the agent saying whatever anyone types."""
    source = inspect.getsource(salon.entrypoint)
    assert 'host_identity = ""' in source
    assert "bool(host_identity) and sender == host_identity" in _handler()


def test_a_guest_is_answered_rather_than_recited():
    handler = _handler()
    assert "generate_reply(user_input=text)" in handler


# ─── What the room sees ───────────────────────────────────────────────────────

def test_the_spoken_line_is_not_also_published_as_a_caption():
    """say() adds an assistant turn, which the conversation_item_added handler already
    publishes. Publishing here as well would print the same sentence twice, once as the host
    and once as the agent, for something the room heard once."""
    handler = _handler()
    spoken = _code(handler[handler.index("if speaks_aloud:") : handler.index("# A guest's typed line")])
    # The only publish left in that branch is the fallback for a say() that threw.
    assert spoken.count("publish_soon") == 1
    assert "except Exception" in spoken[: spoken.index("publish_soon")]


def test_a_guest_line_reaches_the_room_in_writing():
    handler = _handler()
    tail = handler[handler.index("# A guest's typed line") :]
    assert "publish_soon(text=text, identity=sender)" in tail


def test_a_failed_say_still_delivers_the_line():
    """The host wrote something and pressed send. Losing it because the voice failed would be
    the worst of both — no sound and no record."""
    handler = _handler()
    spoken = _code(handler[handler.index("if speaks_aloud:") : handler.index("# A guest's typed line")])
    assert "publish_soon" in spoken[spoken.index("except Exception") :]


# ─── Pausing ──────────────────────────────────────────────────────────────────

def test_nothing_is_spoken_while_the_agent_is_paused():
    """The output is off, so say() would be captioned as speech nobody heard — the caption
    would claim something that did not happen in the room."""
    paused = _code(_handler())
    paused = paused[paused.index('if paused["value"]:') : paused.index("if speaks_aloud:")]
    assert "publish_soon" in paused
    assert "say(" not in paused, "a paused agent must not speak"
    assert "return" in paused


def test_a_paused_agent_still_lets_the_room_reach_itself():
    """Pausing stops the agent taking part. It does not mean the people in it stop being able
    to talk to each other."""
    paused = _code(_handler())
    paused = paused[paused.index('if paused["value"]:') : paused.index("if speaks_aloud:")]
    assert "identity=sender" in paused, "delivered, and attributed to whoever wrote it"


def test_the_pause_is_tracked_rather_than_asked_of_the_session():
    source = inspect.getsource(salon.entrypoint)
    assert 'paused = {"value": starts_paused}' in source
    assert 'paused["value"] = muted' in source


# ─── Length ───────────────────────────────────────────────────────────────────

def test_an_overlong_message_is_cut_rather_than_refused():
    """A caption is read in a scrolling column beside a live conversation. Losing the tail of
    an overlong message is kinder than losing all of it with an error nobody expected."""
    assert "[:_MAX_TYPED_CHARS]" in _handler()
    assert salon._MAX_TYPED_CHARS > 0


def test_an_empty_message_does_nothing():
    assert "if not text" in _handler()


# ─── A human speaking silences the agent ──────────────────────────────────────
#
# The rule is unconditional, and that is the point. It does not wait for the caller to say
# they would rather talk to a person, and it does not check whether anybody asked: somebody
# unmuting in a room is somebody about to speak, and two voices answering one caller is worse
# than either alone.

def test_a_human_unmuting_pauses_the_agent():
    source = inspect.getsource(salon.entrypoint)
    assert 'ctx.room.on("track_unmuted"' in source
    handler = source[source.index("def _on_track_unmuted") :]
    handler = handler[: handler.index('ctx.room.on("track_unmuted"')]
    assert "_pause_for_a_human" in handler


def test_the_agents_own_track_is_ignored():
    """The agent unmutes itself when it is resumed. Reacting to that would pause it again a
    moment after the host let it speak — a control that undoes itself."""
    source = inspect.getsource(salon.entrypoint)
    handler = source[source.index("def _on_track_unmuted") :]
    handler = handler[: handler.index('ctx.room.on("track_unmuted"')]
    assert 'identity == "agent"' in handler


def test_only_audio_counts():
    """A camera coming on is not somebody about to speak."""
    source = inspect.getsource(salon.entrypoint)
    handler = source[source.index("def _on_track_unmuted") :]
    handler = handler[: handler.index('ctx.room.on("track_unmuted"')]
    assert "KIND_AUDIO" in handler


def test_pausing_for_a_human_is_idempotent():
    """The event can arrive more than once — a reconnect republishes tracks — and interrupting
    an agent that is already silent would be a stutter nobody asked for."""
    source = inspect.getsource(salon.entrypoint)
    block = source[source.index("def _pause_for_a_human") :]
    block = block[: block.index("def _on_track_unmuted")]
    assert 'if paused["value"]:' in block
    assert "return" in block


def test_both_directions_are_cut_and_speech_is_interrupted():
    """Mid-sentence is exactly when a human takes over, so stopping the output matters as much
    as stopping the input."""
    source = inspect.getsource(salon.entrypoint)
    block = source[source.index("def _pause_for_a_human") :]
    block = block[: block.index("def _on_track_unmuted")]
    assert "input.set_audio_enabled(False)" in block
    assert "output.set_audio_enabled(False)" in block
    assert "interrupt()" in block


def test_the_arrival_asks_whether_to_hand_over():
    """The caller was promised a signal; being told a human is there without being asked
    anything leaves them guessing whether to keep talking to a machine."""
    source = inspect.getsource(salon.entrypoint)
    assert "would rather speak with the human directly" in source


# ─── The voice connection reports itself ──────────────────────────────────────
#
# xAI offers no cheap voice call to probe: /v1/audio/speech answers 403 for this team, and a
# realtime session is too costly to open every minute purely to ask whether it can be opened.
# So the check is the real thing — this start() either reaches the realtime model or it does not.

def test_the_voice_connection_is_reported_both_ways():
    source = inspect.getsource(salon.entrypoint)
    block = source[source.index("try:\n        await agent_session.start") :]
    block = block[: block.index("mixed_input = ")]
    assert "ok=False" in block
    assert "ok=True" in block


def test_a_failure_is_reported_before_it_is_re_raised():
    """The job is over either way, but somebody has to learn that a Salon just failed for a
    reason invisible from inside Vocaliz — the room looks normal to everyone in it."""
    source = inspect.getsource(salon.entrypoint)
    block = source[source.index("except Exception as exc:  # noqa: BLE001\n        # Reported") :]
    block = block[: block.index("await _report_voice_health(api_url, session_id, host_token, ok=True)")]
    assert block.index("_report_voice_health") < block.index("raise")


def test_reporting_can_never_break_the_salon():
    """A monitor that can break the thing it monitors is worse than no monitor."""
    source = inspect.getsource(salon._report_voice_health)
    assert "except Exception" in source
    assert "logger.warning" in source
