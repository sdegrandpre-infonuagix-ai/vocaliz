"""Where each interpreter has got to in the journal.

The only thing in a Salon that moves. The journal is appended to and never altered, so
everything about the pace of a conversation — who is behind, who needs condensing, who has
been given the history — is a statement about these numbers.

They are independent by construction. One interpreter falling behind slows nobody down,
which is the whole point of giving each participant a room and a reader of their own.
"""
from __future__ import annotations


class Cursors:
    """One position per reader, keyed by whatever identifies it."""

    def __init__(self, positions: dict[str, int] | None = None) -> None:
        self._positions: dict[str, int] = dict(positions or {})

    def __contains__(self, reader_id: str) -> bool:
        return reader_id in self._positions

    @property
    def readers(self) -> tuple[str, ...]:
        return tuple(sorted(self._positions))

    def position_of(self, reader_id: str, *, default: int = 0) -> int:
        """Where this reader is. `default` is where an unknown one counts as being — the
        head for somebody who has just arrived, so they are given what is said from now on."""
        return self._positions.get(reader_id, default)

    def place(self, reader_id: str, position: int) -> int:
        """Put a reader at a position outright.

        Used when one attaches, and only then: Story 6.10 decides between the head and the
        beginning of the journal, and that decision is not a movement forward.
        """
        self._positions[reader_id] = position
        return position

    def advance(self, reader_id: str, position: int, *, head: int | None = None) -> int:
        """Move a position forward. Returns where it ended up.

        Never backwards. A late acknowledgement arriving out of order would otherwise
        replay what has already been said, and a listener cannot tell a repeat from
        somebody saying the same thing twice.
        """
        if head is not None and position > head:
            raise ValueError(
                f"position {position} is past the head of the journal ({head}) "
                f"for reader {reader_id}"
            )

        self._positions[reader_id] = max(self._positions.get(reader_id, 0), position)
        return self._positions[reader_id]

    def remove(self, reader_id: str) -> None:
        self._positions.pop(reader_id, None)

    def as_dict(self) -> dict[str, int]:
        return dict(self._positions)
