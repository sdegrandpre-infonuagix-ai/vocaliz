"""Video, muted, on a path of its own.

It exists because the topology took something away. Nobody hears anybody's real voice any
more — every sentence arrives spoken by a model — so the oldest proof of identity there is,
recognising somebody by how they sound, is gone. Seeing them gives it back, and that is the
entire job.

Everything here follows from it being the *only* job:

- **No sound.** Audio stays entirely in the interpreters' path. Video never opens a second
  channel, because a second channel is a second way for two humans to hear each other, and
  the absence of that is what makes echo unavailable rather than cancelled.
- **A separate path.** Not the interpretation rooms, for the same reason.
- **Never kept.** Lived live and then lost. NFR8 does not reach it: the text journal is what
  a takeover needs and what proves an advertisement was broadcast.
- **A vignette.** 240p at 15 fps under an explicit cap, never the SDK's default — which
  climbs to 720p and multiplies the cost by seven to do a job a thumbnail already does. The
  question is "is that the person I think it is", not "what are they feeling".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.interprete import Participant

# `debit_max_video`. Explicit on purpose: a default left to the SDK is a default that grows
# with the SDK, and at 720p this costs about 15% of the Base tier instead of about 2% — for
# no gain at all in recognising a face.
MAX_VIDEO_BITRATE_KBPS = 200
VIDEO_HEIGHT = 240
VIDEO_FPS = 15


@dataclass(frozen=True)
class VideoTrack:
    """One participant's picture, as it is published.

    `audio` is a field rather than an omission so that the promise is visible in the data:
    anything reading a track can see that it carries none.
    """

    salon_id: str
    participant_id: str
    name: str
    bitrate_kbps: int = MAX_VIDEO_BITRATE_KBPS
    height: int = VIDEO_HEIGHT
    fps: int = VIDEO_FPS
    audio: bool = False


def video_track_name(salon_id: str, participant_id: str) -> str:
    """Derived, like a room name, and deliberately *not* a room name.

    The prefix is what keeps the two media paths apart at a glance — and being derived means
    an instance taking a Salon over can name a track again from what it re-read.
    """
    return f"video--{salon_id}--{participant_id}"


class VideoPath(Protocol):
    """Somewhere for pictures to travel that is not the interpretation rooms.

    Deliberately narrow. There is no method here that could keep a frame, which is how
    "never recorded" is stated in a way that cannot rot.
    """

    async def publish(self, salon_id: str, participant: Participant) -> VideoTrack:
        """Start carrying one participant's picture, muted and capped."""

    async def stop(self, track: VideoTrack) -> None:
        """Stop carrying it. Nothing of it is kept."""


class InMemoryVideoPath:
    """A video path that carries nothing anywhere.

    For tests and for a developer with no LiveKit project. It answers the port exactly, and
    it makes the two guarantees checkable: what is published carries no audio, and nothing
    survives being stopped.
    """

    def __init__(self) -> None:
        self._tracks: dict[str, VideoTrack] = {}

    async def publish(self, salon_id: str, participant: Participant) -> VideoTrack:
        name = video_track_name(salon_id, participant.id)
        track = VideoTrack(salon_id=salon_id, participant_id=participant.id, name=name)
        self._tracks[name] = track
        return track

    async def stop(self, track: VideoTrack) -> None:
        self._tracks.pop(track.name, None)

    # ── For tests ─────────────────────────────────────────────────────────────

    @property
    def tracks(self) -> tuple[VideoTrack, ...]:
        return tuple(self._tracks.values())

    @property
    def published(self) -> tuple[str, ...]:
        return tuple(sorted(self._tracks))

    @property
    def recorded(self) -> tuple[()]:
        """Always empty, and there is no code that could make it otherwise."""
        return ()
