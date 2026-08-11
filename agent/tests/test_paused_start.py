"""A Salon starts with its agent paused, and the host is what starts it.

The agent used to open the conversation on a timer: fifteen seconds after the first invitation
it spoke, whether or not anybody was ready. That interrupted a host still reading their own
screen and made one who was ready sit through a counter. The countdown is gone; the agent joins
in silence and speaks when the host activates it.

Read out of the entrypoint's source rather than by running it. The entrypoint needs a LiveKit
room, a realtime model and a live API before it will do anything at all, and the four facts
below are worth pinning even where the wiring cannot be exercised — each of them, wrong, is a
Salon that either never speaks or speaks over its host.
"""
import inspect

import agent as salon


def _entrypoint() -> str:
    return inspect.getsource(salon.entrypoint)


def test_silence_is_what_an_unreachable_api_falls_back_to():
    """The default when the salon detail cannot be read at all. Joining a room and
    immediately talking is the one outcome nobody asked for, so an unanswered fetch must not
    produce it."""
    source = _entrypoint()
    assert "starts_paused = True" in source
    at_default = source.index("starts_paused = True")
    at_read = source.index('detail.get("agentMuted"')
    assert at_default < at_read, "the default must be set before the detail can overwrite it"


def test_the_pause_is_read_from_the_salon_rather_than_assumed():
    """An agent can join a Salon that is already under way — a restarted job, or one the host
    removed and brought back. Hard-coding the pause would rejoin that room in silence."""
    assert 'detail.get("agentMuted", True)' in _entrypoint()


def test_the_audio_is_enabled_before_it_is_paused():
    """Not a redundant pair of calls. Enabling is what attaches the mixer — the transition into
    True is the only moment that happens — so starting at False would leave a mixer nothing
    ever consumes, and the host's activate button would restore nothing."""
    source = _entrypoint()
    enable = source.index("agent_session.input.set_audio_enabled(True)")
    pause = source.index("if starts_paused:")
    assert enable < pause


def test_both_directions_are_cut_while_paused():
    """Output alone would leave the agent listening to a conversation its host believes is
    private, which is the opposite of what pausing means here."""
    block = _entrypoint()
    block = block[block.index("if starts_paused:") :][:400]
    assert "input.set_audio_enabled(False)" in block
    assert "output.set_audio_enabled(False)" in block


def test_activating_opens_the_conversation():
    """The press has to produce speech. Enabling the audio and waiting to be spoken to would
    answer the host's button with silence — the complaint the opening exists to fix."""
    source = _entrypoint()
    handler = source[source.index('msg.get("action") == "agent_mute"') :]
    handler = handler[: handler.index("elif isinstance(msg")]
    assert "opening.schedule(0)" in handler
    assert "if not muted:" in handler


def test_an_unpaused_salon_opens_on_arrival():
    """A Salon starts with its agent listening, so there is no button coming and nothing to
    wait for. Waiting would be silence the host cannot end.

    The paused default was tried for an afternoon and reversed; pausing survives as a control
    rather than a starting gate.

    Also gated on `not follow_journal` since Story 11.1: `_speak_the_opening` improvises its
    own account of what Vocaliz and a Salon are, which produced a doubled welcome once the
    per-participant topology added its own canonical, non-improvised one."""
    source = _entrypoint()
    assert "if not starts_paused and not follow_journal:" in source
    assert "opening.schedule(0)" in source


def test_nothing_still_waits_on_an_invitation():
    """The countdown and the message that drove it are both gone. A surviving reference would
    be an opening that fires on a timer again, next to one that fires on the button."""
    source = _entrypoint()
    assert "guest_invited" not in source
    assert "opensInSeconds" not in source
    assert not hasattr(salon, "INVITATION_OPENING_SECONDS")


# ─── The voice model is pinned per tier, never aliased ────────────────────────

def test_the_voice_model_is_named_explicitly():
    """An alias lets the model change under a running product without a deploy, and a voice, a
    latency and a price moving on their own is a behaviour change nobody can attribute
    afterwards."""
    source = inspect.getsource(salon.entrypoint)
    assert '"grok-voice-think-fast-1.0"' in source
    assert '"grok-voice-think-fast-2.0"' in source
    assert 'model="grok-voice-latest"' not in source
    assert 'model=xai_model' in source


def _xai_model_block() -> str:
    source = inspect.getsource(salon.entrypoint)
    block = source[source.index("xai_model = ") :]
    return block[: block.index("turn_handling = {")]


def test_mode_a_runs_on_the_cheaper_model():
    """$0.08/min ($4.80/h) leaves real margin against Mode A's $7.50/h, but Mode A's whole
    pitch is costing less than B and C for a plainer interpreter — 2.0 is the thing B and C
    are selling instead."""
    block = _xai_model_block()
    assert '"grok-voice-think-fast-1.0"' in block
    assert 'else' in block


def test_mode_b_and_mode_c_run_on_the_better_model():
    """Both sell being better than Mode A as the entire reason to cost more — before this,
    every tier ran on the same model, which is exactly the gap a host testing Mode C against
    Mode A could hear and report as "not working"."""
    block = _xai_model_block()
    assert '"Mode B", "Mode C"' in block
    assert '"grok-voice-think-fast-2.0"' in block


def test_the_tier_comes_from_the_salon_not_a_guess():
    source = inspect.getsource(salon.entrypoint)
    assert 'host_tier = "Base"' in source
    assert 'detail.get("hostTier")' in source


# ─── Base gets the STT+TTS adapter, not a cheaper realtime model ──────────────


def _base_branch() -> str:
    source = inspect.getsource(salon.entrypoint)
    start = source.index('if host_tier == "Base":')
    end = source.index("else:", start)
    return source[start:end]


def test_base_does_not_use_the_realtime_model_at_all():
    """The PRD's third adapter — transcribe, render, synthesise — not the realtime model
    under a cheaper name. Before this, Base and Mode A were the same pipeline with a
    cheaper label on one of them."""
    block = _base_branch()
    assert 'xai.realtime.RealtimeModel' not in block
    assert 'llm=xai.responses.LLM(' in block
    assert 'stt=xai.STT(' in block
    assert 'tts=xai.TTS(' in block


def test_base_uses_the_cheapest_text_model():
    block = _base_branch()
    assert 'model="grok-4-1-fast-non-reasoning"' in block


def test_base_still_sounds_like_the_chosen_voice():
    """The cheaper price is the differentiator; the voice was not asked to sound it too."""
    block = _base_branch()
    assert 'voice=chosen_voice' in block


def test_base_transcribes_the_forced_language_or_falls_back_to_english():
    """The realtime model's auto-follow-each-speaker behaviour has no equivalent for a
    standalone STT step, so a participant with no override is transcribed as English — same
    fallback `listener_language` already uses elsewhere for the same reason."""
    block = _base_branch()
    assert 'forced_language if forced_language != "auto" else "en"' in block
