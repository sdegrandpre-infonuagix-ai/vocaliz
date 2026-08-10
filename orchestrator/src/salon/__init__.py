"""A Salon in progress: one room and one interpreter per participant, over one journal.

`rooms` is what makes echo unavailable rather than cancelled — one human per room, always.
`conductor` is what ties that to the journal of Story 6.3 and the Interpreter port of 6.2.
"""
from src.salon.advertising import Diffusion, Regie, RegieFake
from src.salon.conductor import NotTheHost, Salon
from src.salon.history import (
    DEFAULT_HISTORY_FOR_ARRIVALS,
    HistoryAccess,
    grants_history,
    history_from_invitation,
)
from src.salon.notices import (
    call_declined,
    call_not_answered,
    caller_hung_up,
    history_shared_with,
    microphone_cut,
    microphone_restored,
    on_the_telephone,
    telephone_greeting,
)
from src.salon.meta_speech import MetaSpeechQueue, Urgency
from src.salon.speaking import Pair, SpeakingBoard, Voice
from src.salon.captions import (
    AS_SPOKEN,
    DEFAULT_CAPTION_SCALE,
    caption_languages,
    captions_offered_in,
)
from src.salon.video import (
    MAX_VIDEO_BITRATE_KBPS,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    InMemoryVideoPath,
    VideoPath,
    VideoTrack,
    video_track_name,
)
from src.salon.rooms import (
    InMemoryRoomProvisioner,
    Room,
    RoomClosed,
    RoomProvisioner,
    interpreter_identity,
    room_name,
)
from src.salon.notify import FailingNotifier, NoNotifier, Notifier, RecordingNotifier

__all__ = [
    "DEFAULT_HISTORY_FOR_ARRIVALS",
    "HistoryAccess",
    "AS_SPOKEN",
    "DEFAULT_CAPTION_SCALE",
    "Diffusion",
    "FailingNotifier",
    "InMemoryRoomProvisioner",
    "InMemoryVideoPath",
    "MAX_VIDEO_BITRATE_KBPS",
    "MetaSpeechQueue",
    "NoNotifier",
    "Notifier",
    "RecordingNotifier",
    "Urgency",
    "VIDEO_FPS",
    "VIDEO_HEIGHT",
    "VideoPath",
    "VideoTrack",
    "NotTheHost",
    "Room",
    "RoomClosed",
    "RoomProvisioner",
    "Pair",
    "Regie",
    "RegieFake",
    "Salon",
    "SpeakingBoard",
    "Voice",
    "interpreter_identity",
    "grants_history",
    "history_from_invitation",
    "history_shared_with",
    "microphone_cut",
    "microphone_restored",
    "on_the_telephone",
    "call_declined",
    "call_not_answered",
    "caller_hung_up",
    "telephone_greeting",
    "caption_languages",
    "captions_offered_in",
    "room_name",
    "video_track_name",
]
