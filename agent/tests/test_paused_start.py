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
    """The default when the session detail cannot be read at all. Joining a room and
    immediately talking is the one outcome nobody asked for, so an unanswered fetch must not
    produce it."""
    source = _entrypoint()
    assert "starts_paused = True" in source
    at_default = source.index("starts_paused = True")
    at_read = source.index('detail.get("agentMuted"')
    assert at_default < at_read, "the default must be set before the detail can overwrite it"


def test_the_pause_is_read_from_the_session_rather_than_assumed():
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


def test_a_salon_already_running_settles_the_gate_instead():
    """Otherwise the host's next pause and resume is answered with a welcome to a room that
    has been talking for ten minutes."""
    source = _entrypoint()
    assert "if not starts_paused:" in source
    assert "opening.settle()" in source


def test_nothing_still_waits_on_an_invitation():
    """The countdown and the message that drove it are both gone. A surviving reference would
    be an opening that fires on a timer again, next to one that fires on the button."""
    source = _entrypoint()
    assert "guest_invited" not in source
    assert "opensInSeconds" not in source
    assert not hasattr(salon, "INVITATION_OPENING_SECONDS")
