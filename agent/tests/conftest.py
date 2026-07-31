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

    # livekit.agents ── Agent base class, function_tool passthrough, etc.
    agents_mod = _register_stub(
        "livekit.agents",
        Agent=_AgentBase,
        AgentSession=MagicMock,
        RoomInputOptions=MagicMock,
        JobContext=MagicMock,
        function_tool=lambda f: f,  # passthrough — keeps the function callable
        cli=MagicMock(),
        WorkerOptions=MagicMock,
    )

    # livekit (parent)
    livekit_mod = _register_stub("livekit", agents=agents_mod)

    # plugins
    xai_realtime = MagicMock()
    xai_mod = _register_stub("livekit.plugins.xai", realtime=xai_realtime)
    silero_mod = _register_stub("livekit.plugins.silero", VAD=MagicMock())
    # EOUModel was removed from the real plugin; agent.py now imports the multilingual
    # submodule, so the stub has to expose it as a package attribute too.
    td_multilingual = _register_stub(
        "livekit.plugins.turn_detector.multilingual", MultilingualModel=MagicMock
    )
    td_mod = _register_stub(
        "livekit.plugins.turn_detector", multilingual=td_multilingual
    )
    plugins_mod = _register_stub(
        "livekit.plugins", xai=xai_mod, silero=silero_mod, turn_detector=td_mod
    )

    # dotenv — just a no-op
    _register_stub("dotenv", load_dotenv=lambda: None)


_build_livekit_stubs()
