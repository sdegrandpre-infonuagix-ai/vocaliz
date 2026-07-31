"""Audio input that merges every remote participant into one stream.

livekit-agents' RoomIO binds the session to a single participant: its
`_ParticipantAudioInputStream` takes one `participant_identity`, and `set_participant()`
only switches between them. In a Salon session that means the agent hears whoever joined
first and is deaf to the other — which breaks facilitation of a two-way conversation
(FR9) and translation between participants outright (FR14–FR17).

This replaces the input side only. The agent still publishes a single shared output to
the room, so the PRD's "one shared Voice Agent, single audio stream" holds.

Design notes:
  * Each remote track is read through rtc.AudioStream with an explicit sample_rate,
    num_channels and frame_size_ms, so the SDK resamples for us and every buffer holds
    directly comparable samples. No resampling code here.
  * A fixed-cadence ticker emits one mixed frame per interval rather than reacting to
    incoming frames: participants arrive at slightly different rates, and mixing on
    arrival would let the fastest talker set the pace and starve the others.
  * A participant with nothing buffered contributes silence, so one person going quiet
    never stalls the mix.
"""

from __future__ import annotations

import asyncio
import logging

import numpy as np
from livekit import rtc
from livekit.agents.voice.io import AudioInput

logger = logging.getLogger("salon-agent")

SAMPLE_RATE = 24000
NUM_CHANNELS = 1
FRAME_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000

# Bounded so a stalled consumer drops audio instead of growing without limit.
_QUEUE_FRAMES = 50           # 1 s at 20 ms
_MAX_BUFFERED_SAMPLES = SAMPLE_RATE * 2   # 2 s per participant


class MixedParticipantAudioInput(AudioInput):
    """Sums the audio of all remote participants into a single frame stream."""

    def __init__(self, room: rtc.Room) -> None:
        super().__init__(label="salon.MixedParticipantAudioInput")
        self._room = room
        self._buffers: dict[str, np.ndarray] = {}
        self._readers: dict[str, asyncio.Task] = {}
        self._queue: asyncio.Queue[rtc.AudioFrame] = asyncio.Queue(maxsize=_QUEUE_FRAMES)
        self._ticker: asyncio.Task | None = None
        self._closed = False

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Attach room handlers and begin mixing."""
        self._room.on("track_subscribed", self._on_track_subscribed)
        self._room.on("track_unsubscribed", self._on_track_unsubscribed)

        # Tracks already subscribed before we attached would otherwise be missed.
        for participant in self._room.remote_participants.values():
            for pub in participant.track_publications.values():
                if pub.track and pub.kind == rtc.TrackKind.KIND_AUDIO:
                    self._add_track(participant.identity, pub.track)

        self._ticker = asyncio.create_task(self._mix_loop())
        logger.info("Mixed audio input started (%d Hz, %d ms frames)", SAMPLE_RATE, FRAME_MS)

    async def aclose(self) -> None:
        self._closed = True
        self._room.off("track_subscribed", self._on_track_subscribed)
        self._room.off("track_unsubscribed", self._on_track_unsubscribed)
        for task in list(self._readers.values()):
            task.cancel()
        self._readers.clear()
        self._buffers.clear()
        if self._ticker:
            self._ticker.cancel()
            self._ticker = None

    # ── AudioInput contract ──────────────────────────────────────────────────

    async def __anext__(self) -> rtc.AudioFrame:
        if self._closed:
            raise StopAsyncIteration
        return await self._queue.get()

    # ── room events ──────────────────────────────────────────────────────────

    def _on_track_subscribed(self, track, publication, participant) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            self._add_track(participant.identity, track)

    def _on_track_unsubscribed(self, track, publication, participant) -> None:
        identity = participant.identity
        task = self._readers.pop(identity, None)
        if task:
            task.cancel()
        self._buffers.pop(identity, None)
        logger.info("Removed %s from the mix (%d remaining)", identity, len(self._readers))

    def _add_track(self, identity: str, track) -> None:
        if identity in self._readers:
            return
        self._buffers[identity] = np.zeros(0, dtype=np.int16)
        self._readers[identity] = asyncio.create_task(self._read_track(identity, track))
        logger.info("Added %s to the mix (%d participants)", identity, len(self._readers))

    # ── per-participant reader ───────────────────────────────────────────────

    async def _read_track(self, identity: str, track) -> None:
        """Buffer one participant's samples, already resampled by the SDK."""
        stream = rtc.AudioStream(
            track,
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            frame_size_ms=FRAME_MS,
        )
        try:
            async for event in stream:
                samples = np.frombuffer(event.frame.data, dtype=np.int16)
                buffered = self._buffers.get(identity)
                if buffered is None:
                    break  # unsubscribed while we were awaiting
                combined = np.concatenate((buffered, samples))
                # Drop the oldest audio rather than let a backlog grow unbounded: stale
                # speech is worse than missing speech for a live conversation.
                if combined.size > _MAX_BUFFERED_SAMPLES:
                    combined = combined[-_MAX_BUFFERED_SAMPLES:]
                self._buffers[identity] = combined
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Audio reader failed for %s", identity)
        finally:
            await stream.aclose()

    # ── mixer ────────────────────────────────────────────────────────────────

    def _take(self, identity: str) -> np.ndarray:
        """Pop one frame's worth for a participant, padding with silence if short."""
        buffered = self._buffers.get(identity)
        if buffered is None or buffered.size == 0:
            return np.zeros(SAMPLES_PER_FRAME, dtype=np.int32)

        chunk = buffered[:SAMPLES_PER_FRAME]
        self._buffers[identity] = buffered[SAMPLES_PER_FRAME:]
        if chunk.size < SAMPLES_PER_FRAME:
            chunk = np.pad(chunk, (0, SAMPLES_PER_FRAME - chunk.size))
        # int32 so summing several participants cannot wrap before clipping.
        return chunk.astype(np.int32)

    async def _mix_loop(self) -> None:
        interval = FRAME_MS / 1000
        try:
            while not self._closed:
                await asyncio.sleep(interval)

                identities = list(self._buffers.keys())
                if not identities:
                    continue

                mixed = np.zeros(SAMPLES_PER_FRAME, dtype=np.int32)
                for identity in identities:
                    mixed += self._take(identity)

                # Clip rather than normalise: normalising would pump the gain up and down
                # as people start and stop talking, which the VAD reads as noise.
                clipped = np.clip(mixed, -32768, 32767).astype(np.int16)

                frame = rtc.AudioFrame(
                    data=clipped.tobytes(),
                    sample_rate=SAMPLE_RATE,
                    num_channels=NUM_CHANNELS,
                    samples_per_channel=SAMPLES_PER_FRAME,
                )
                try:
                    self._queue.put_nowait(frame)
                except asyncio.QueueFull:
                    # Consumer is behind; drop this frame so the mixer keeps real time.
                    pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Mixer loop failed")
