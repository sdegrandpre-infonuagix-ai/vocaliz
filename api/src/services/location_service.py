"""Where a participant was, to the nearest neighbourhood and no closer.

Positions are stored as Open Location Codes — Google Plus Codes — rather than as
latitude and longitude. The reason is not compactness: a pair of decimals still reads as
a point, and a point invites being treated as one. A Plus Code *is* a grid cell, so the
imprecision is part of the value instead of a convention someone has to remember.

The grid is base 20, which means precision jumps by a factor of twenty between rungs and
there is no neighbourhood-sized one:

    4 digits   111 km      a region
    6 digits   5.5 km      a borough
    8 digits   275 m       a block
    10 digits  14 m        a doorstep

Six is the default. Eight is nearer the literal size of a neighbourhood, but in anything
less than a dense city it narrows to a handful of houses, which is an approximate address
rather than an approximate area.
"""
import logging

from openlocationcode import openlocationcode as olc

from src.config import settings

logger = logging.getLogger(__name__)


def plus_code(latitude: float | None, longitude: float | None) -> str:
    """A Plus Code for this position, or "" when there is no position.

    Empty rather than None because this lands in a column alongside the identity ones,
    which use the same convention: absent is a value we can compare, not a NULL that
    behaves differently in every query.

    Encoded here, at ingestion, and never stored precisely first. Rounding on the way out
    would leave the exact coordinates at rest, which is the thing worth avoiding.
    """
    if latitude is None or longitude is None:
        return ""
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        logger.warning("Position was not a pair of numbers")
        return ""

    # Checked here because the encoder does not. encode(999, 999) returns "C6XXX200+" —
    # a well-formed code for a place that does not exist, arrived at by clamping the
    # latitude and wrapping the longitude. A bad reading must produce no location, not a
    # plausible one somewhere near the pole.
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        logger.warning("Position out of range, not recorded")
        return ""

    try:
        return olc.encode(lat, lon, codeLength=settings.location_code_length)
    except Exception:  # noqa: BLE001
        # A position outside the valid range, or a value that is not a number at all.
        # Losing it costs a row's location and nothing else.
        logger.warning("Could not encode a position", exc_info=True)
        return ""


def approximate_centre(code: str) -> tuple[float, float] | None:
    """The centre of a coded cell, for distance work.

    Advertiser targeting draws a circle and asks who is inside it. That needs a number,
    and the honest number is the middle of the cell the participant was placed in — with
    the cell's own size as the error bar. At six digits that error is a few kilometres,
    so a radius smaller than that cannot mean anything.
    """
    if not code:
        return None
    try:
        area = olc.decode(code)
        return area.latitudeCenter, area.longitudeCenter
    except Exception:  # noqa: BLE001
        logger.warning("Could not decode %s", code, exc_info=True)
        return None


# ─── The address half, which does not exist ──────────────────────────────────
#
# A position is only ever available when the participant granted it, and declining is the
# common case. Deriving one from the caller's IP address instead would need either a
# GeoIP database shipped in the Lambda image or a lookup service called per join, and
# neither is here.
#
# Until one is, a participant who declines the location prompt has no recorded location
# at all. The raw address is no longer kept either: storing an IP in order to maybe
# geocode it one day is keeping personal data against a plan, not against a use.
