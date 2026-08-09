"""Simulated participants and the load harness (FR58 / NFR4).

The purpose is a decision: raising the participant ceiling from 3 to 50 should be a
measurement rather than a bet, which requires running 50 participants without paying a
provider for any of them.
"""
from src.load.metrics import SalonMetrics, Tier
from src.load.report import (
    PASS_BLOCK_WINDOW_SECONDS,
    PASS_CONDENSED_RATIO,
    PASS_COST_SHARE,
    PASS_LATENCY_SECONDS,
    Report,
    TierPrice,
)
from src.load.speaker import SimulatedSpeaker

__all__ = [
    "PASS_BLOCK_WINDOW_SECONDS",
    "PASS_CONDENSED_RATIO",
    "PASS_COST_SHARE",
    "PASS_LATENCY_SECONDS",
    "Report",
    "SalonMetrics",
    "SimulatedSpeaker",
    "Tier",
    "TierPrice",
]
