"""The interpreter's voice, as xAI's realtime API offers it (FR — host-chosen voice).

Named here once so the create-salon validation and anything else that needs the list read
the same catalogue the plugin accepts, rather than a copy that can drift from it.
"""
from __future__ import annotations

# Every voice id `livekit.plugins.xai.realtime.RealtimeModel` accepts, alphabetical except for
# the default, which leads the list because that is where a combo box puts it.
XAI_VOICES: tuple[str, ...] = (
    "ara",
    "altair",
    "atlas",
    "carina",
    "castor",
    "celeste",
    "cosmo",
    "eve",
    "helios",
    "helix",
    "iris",
    "kepler",
    "leo",
    "lumen",
    "luna",
    "lux",
    "naksh",
    "orion",
    "perseus",
    "rex",
    "rigel",
    "sal",
    "sirius",
    "ursa",
    "zagan",
    "zenith",
)

DEFAULT_VOICE = "ara"


def is_supported(voice: str) -> bool:
    return voice in XAI_VOICES
