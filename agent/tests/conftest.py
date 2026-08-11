"""
Stub out livekit and dotenv so agent.py can be imported without installing
the full livekit-agents package in the test environment.
"""
import sys
import types
from unittest.mock import MagicMock


def _register_stub(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _build_livekit_stubs() -> None:
    if "livekit" in sys.modules:
        return

    # Agent base class that accepts keyword args (mirrors livekit.agents.Agent)
    class _AgentBase:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    # livekit.agents.inference ── turn detection moved here from the deprecated
    # livekit.plugins.turn_detector package.
    inference_mod = _register_stub("livekit.agents.inference", TurnDetector=MagicMock)

    # Raised from `Agent.on_user_turn_completed` to skip the framework's automatic reply for
    # that turn (mirrors livekit.agents.StopResponse, defined for real in llm/tool_context.py
    # — a submodule this stub package does not have, so importing it from there would fail
    # exactly as it does at the top level when the stub lacks the name).
    class _StopResponse(Exception):
        pass

    # livekit.agents ── Agent base class, function_tool passthrough, etc.
    agents_mod = _register_stub(
        "livekit.agents",
        Agent=_AgentBase,
        AgentSession=MagicMock,
        JobContext=MagicMock,
        StopResponse=_StopResponse,
        function_tool=lambda f: f,  # passthrough — keeps the function callable
        inference=inference_mod,
        cli=MagicMock(),
        WorkerOptions=MagicMock,
    )

    # livekit.agents.voice.io ── AudioInput base class, subclassed by our mixer
    class _AudioInputBase:
        def __init__(self, *, label, source=None):
            self._label = label
            self._source = source

        def __aiter__(self):
            return self

    io_mod = _register_stub("livekit.agents.voice.io", AudioInput=_AudioInputBase)
    # RoomOptions replaced RoomInputOptions/RoomOutputOptions and is not re-exported at
    # the livekit.agents top level, so agent.py imports it from this submodule.
    room_io_mod = _register_stub("livekit.agents.voice.room_io", RoomOptions=MagicMock)
    _register_stub("livekit.agents.voice", io=io_mod, room_io=room_io_mod)

    # livekit.rtc ── audio primitives used by the mixer
    class _TrackKind:
        KIND_AUDIO = "audio"

    rtc_mod = _register_stub(
        "livekit.rtc",
        TrackKind=_TrackKind,
        AudioStream=MagicMock,
        AudioFrame=MagicMock,
        Room=MagicMock,
        RemoteParticipant=MagicMock,
    )

    # livekit.api ── server-side room operations (participant attribute updates for the
    # voice-triggered privacy toggle). Only the request type is constructed by agent.py;
    # nothing here calls the real service, so a bare MagicMock is enough to stand in for it.
    api_mod = _register_stub(
        "livekit.api", UpdateParticipantRequest=MagicMock, LiveKitAPI=MagicMock
    )

    # livekit (parent)
    livekit_mod = _register_stub("livekit", agents=agents_mod, rtc=rtc_mod, api=api_mod)

    # plugins
    xai_realtime = MagicMock()
    xai_mod = _register_stub(
        "livekit.plugins.xai", realtime=xai_realtime, WebSearch=MagicMock, XSearch=MagicMock
    )
    silero_mod = _register_stub("livekit.plugins.silero", VAD=MagicMock())
    # livekit.plugins.turn_detector is gone from agent.py: it was deprecated, and it never
    # ran anyway for want of PyTorch. Turn detection now comes from livekit.agents.inference.
    plugins_mod = _register_stub("livekit.plugins", xai=xai_mod, silero=silero_mod)

    # dotenv — just a no-op
    # Accepts override= since agent.py calls load_dotenv(override=True).
    _register_stub("dotenv", load_dotenv=lambda *a, **kw: None)


_build_livekit_stubs()
