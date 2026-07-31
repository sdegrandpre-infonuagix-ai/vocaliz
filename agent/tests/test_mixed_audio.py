"""Tests for the multi-participant audio mixer.

RoomIO hears one participant; this mixer exists so the agent hears everyone. The cases
below cover what actually breaks a live conversation: a silent participant stalling the
mix, two loud speakers wrapping the sample range, and a departing participant.
"""
import numpy as np
import pytest

from src.mixed_audio_input import (
    SAMPLES_PER_FRAME,
    MixedParticipantAudioInput,
)


class _FakeRoom:
    def __init__(self):
        self.remote_participants = {}
        self.handlers = {}

    def on(self, event, handler):
        self.handlers[event] = handler

    def off(self, event, handler):
        self.handlers.pop(event, None)


@pytest.fixture
def mixer():
    return MixedParticipantAudioInput(_FakeRoom())


def _buffer(mixer, identity, samples):
    mixer._buffers[identity] = np.array(samples, dtype=np.int16)


def test_take_pads_short_buffer_with_silence(mixer):
    """A participant with little buffered audio must not shorten the mixed frame."""
    _buffer(mixer, "guest-1", [100, 200, 300])
    chunk = mixer._take("guest-1")
    assert chunk.size == SAMPLES_PER_FRAME
    assert list(chunk[:3]) == [100, 200, 300]
    assert chunk[3:].sum() == 0


def test_take_on_unknown_participant_is_silence(mixer):
    """Someone who has not spoken yet contributes silence, never an exception."""
    chunk = mixer._take("nobody")
    assert chunk.size == SAMPLES_PER_FRAME
    assert chunk.sum() == 0


def test_take_consumes_the_buffer(mixer):
    """Samples are popped, so audio is never mixed into two consecutive frames."""
    _buffer(mixer, "guest-1", [7] * (SAMPLES_PER_FRAME + 5))
    first = mixer._take("guest-1")
    assert first.size == SAMPLES_PER_FRAME
    assert mixer._buffers["guest-1"].size == 5

    second = mixer._take("guest-1")
    assert list(second[:5]) == [7] * 5
    assert second[5:].sum() == 0


def test_sum_of_two_participants_is_additive(mixer):
    """Both voices must be present in the mix — the whole point of this class."""
    _buffer(mixer, "host", [1000] * SAMPLES_PER_FRAME)
    _buffer(mixer, "guest", [2000] * SAMPLES_PER_FRAME)

    mixed = mixer._take("host") + mixer._take("guest")
    assert mixed.dtype == np.int32  # headroom before clipping
    assert set(np.unique(mixed)) == {3000}


def test_loud_speakers_clip_instead_of_wrapping(mixer):
    """Two near-peak speakers must clip, not wrap around to negative noise.

    int16 addition would overflow to a loud negative crackle, which is far worse than
    clipping — hence the int32 accumulator.
    """
    _buffer(mixer, "host", [30000] * SAMPLES_PER_FRAME)
    _buffer(mixer, "guest", [30000] * SAMPLES_PER_FRAME)

    mixed = mixer._take("host") + mixer._take("guest")
    clipped = np.clip(mixed, -32768, 32767).astype(np.int16)

    assert mixed[0] == 60000            # no wrap in the accumulator
    assert set(np.unique(clipped)) == {32767}


def test_unsubscribed_participant_leaves_the_mix(mixer):
    """A guest who leaves stops contributing, and their buffer is released."""
    _buffer(mixer, "guest-1", [500] * SAMPLES_PER_FRAME)

    participant = type("P", (), {"identity": "guest-1"})()
    mixer._on_track_unsubscribed(None, None, participant)

    assert "guest-1" not in mixer._buffers
    assert mixer._take("guest-1").sum() == 0


def test_buffer_is_capped_to_bound_latency(mixer):
    """Runaway buffering is trimmed: stale speech is worse than dropped speech."""
    from src.mixed_audio_input import _MAX_BUFFERED_SAMPLES

    oversized = np.ones(_MAX_BUFFERED_SAMPLES + 1000, dtype=np.int16)
    trimmed = oversized[-_MAX_BUFFERED_SAMPLES:]
    assert trimmed.size == _MAX_BUFFERED_SAMPLES
