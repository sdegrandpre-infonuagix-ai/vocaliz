"""The Salon's operational parameters, and the orderings between them (FR54).

Deliberately not in `src/config.py`. That module holds what the *service* needs to start —
credentials, ports, a region — and it is right that changing any of it means a deploy. These
are different: they are numbers somebody will want to move while a Salon is running badly,
and putting a tuning knob behind a deployment means in practice it never gets turned.

Two of the rules here look like ordinary validation and are not. Both encode an ordering
that, when broken, raises nothing anywhere: the system simply stops doing something it was
built to do, silently, for as long as nobody looks. Refusing the configuration is the only
moment either mistake is visible.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

# The starting values, in one place so the documentation, the tests and the constructor
# cannot drift apart. A parameter is added here and nowhere else.
DEFAULTS: dict[str, float | int] = {
    # Above this lag an interpreter condenses rather than replays (FR53, Story 7.2).
    "condensation_threshold_seconds": 120.0,
    # Above this a room is saturated: it signals, and stops accepting new messages (FR55).
    "saturation_threshold_seconds": 300.0,
    # And below this it is let go again — a second, lower number on purpose (FR55).
    "unblock_threshold_seconds": 240.0,
    # Longer interventions are cut into consecutive journal messages (Story 6.6).
    "max_message_characters": 500,
    # A silence longer than this is content rather than breathing (Story 6.11).
    "significant_pause_ms": 2000,
    # And no pause is ever reported as longer than this.
    "max_pause_ms": 5000,
}


class InvalidSettings(ValueError):
    """Raised when a combination of parameters would not do what it appears to say.

    Always names the fields *and* the values. An error that names only the fields sends
    somebody back to the table to find out what they just typed.
    """


@dataclass(frozen=True)
class SalonSettings:
    condensation_threshold_seconds: float = DEFAULTS["condensation_threshold_seconds"]
    saturation_threshold_seconds: float = DEFAULTS["saturation_threshold_seconds"]
    unblock_threshold_seconds: float = DEFAULTS["unblock_threshold_seconds"]
    max_message_characters: int = DEFAULTS["max_message_characters"]
    significant_pause_ms: int = DEFAULTS["significant_pause_ms"]
    max_pause_ms: int = DEFAULTS["max_pause_ms"]

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            # The table has one numeric column for every parameter, so an integer comes back
            # from it as a float. `max_message_characters` is a length that slices text, so
            # this is the place that has to put the type back — declaring it is not doing it.
            # `field.type` is the string "int" rather than the type: this module uses
            # postponed annotations, so nothing here is ever evaluated into a class.
            if field.type in (int, "int") and isinstance(value, float) and value.is_integer():
                object.__setattr__(self, field.name, int(value))
                value = int(value)
            if value <= 0:
                raise InvalidSettings(
                    f"{field.name} is {value!r}, and every parameter here is a duration or a "
                    "length: zero or less has no meaning."
                )

        if self.condensation_threshold_seconds >= self.saturation_threshold_seconds:
            raise InvalidSettings(
                f"condensation_threshold_seconds ({self.condensation_threshold_seconds:g}) must "
                f"be below saturation_threshold_seconds ({self.saturation_threshold_seconds:g}). "
                "Otherwise condensation would never once run before the alarm it exists to "
                "prevent, and nothing would report that it had stopped working."
            )

        if self.unblock_threshold_seconds >= self.saturation_threshold_seconds:
            raise InvalidSettings(
                f"unblock_threshold_seconds ({self.unblock_threshold_seconds:g}) must be below "
                f"saturation_threshold_seconds ({self.saturation_threshold_seconds:g}). "
                "Otherwise a room would unblock straight back into the condition that blocked "
                "it, oscillating between the two."
            )

    def replace(self, **changes: float | int) -> SalonSettings:
        """A copy with some values changed, validated as a whole.

        Whole rather than field by field, because these rules are about pairs: 250 is a fine
        condensation threshold on its own and wrong beside a saturation threshold of 200.
        """
        return from_mapping({**asdict(self), **changes})


def from_mapping(values: dict[str, object]) -> SalonSettings:
    """Build settings from a stored row, refusing names it does not know.

    An unrecognised key is a typo, and ignoring it would make a change that was apparently
    saved do nothing at all — the least debuggable outcome available.
    """
    known = {field.name for field in fields(SalonSettings)}
    unknown = sorted(set(values) - known)
    if unknown:
        raise InvalidSettings(
            f"unknown parameter(s) {', '.join(unknown)}. Known parameters are "
            f"{', '.join(sorted(known))}."
        )
    return SalonSettings(**values)  # type: ignore[arg-type]
