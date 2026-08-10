""""Forward your last message to the Salon" — a participant's own interpreter, asked to
share what it just told them with everyone else, not just them.

`report()` is the same call a typed line already uses to reach the rest of the Salon (see
`agent.py`'s `text_message` handling): each other participant's own interpreter picks it up
through `follow()` and speaks it in their own language. What is new here is *what* gets
reported — the interpreter's own last utterance, tracked from every assistant turn
(`_on_agent_speech` in `entrypoint`) rather than something the participant said.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agent as salon  # noqa: E402


class _FakeLink:
    """Stands in for `OrchestratorLink`: only `report` is exercised here."""

    def __init__(self, recorded: int = 1) -> None:
        self.reported: list[str] = []
        self._recorded = recorded

    async def report(self, text: str) -> int:
        self.reported.append(text)
        return self._recorded


def test_nothing_said_yet_has_nothing_to_forward():
    agent = salon.SalonAgent(follow_journal=True)
    agent.set_journal_link(_FakeLink())

    assert asyncio.run(agent.forward_last_message_to_salon()) == "nothing_to_forward"


def test_a_blank_utterance_is_never_remembered_as_the_last_one():
    agent = salon.SalonAgent(follow_journal=True)
    agent.set_journal_link(_FakeLink())
    agent.note_spoken("   ")

    assert asyncio.run(agent.forward_last_message_to_salon()) == "nothing_to_forward"


def test_without_a_journal_link_the_salon_is_not_reachable():
    agent = salon.SalonAgent(follow_journal=True)
    agent.note_spoken("Bonjour")

    assert asyncio.run(agent.forward_last_message_to_salon()) == "not_available"


def test_outside_the_journal_topology_the_salon_is_not_reachable():
    """`follow_journal=False` is the one-room, no-orchestrator mode — there is no Salon
    beyond this room to forward into, even if a link were somehow set."""
    agent = salon.SalonAgent(follow_journal=False)
    agent.set_journal_link(_FakeLink())
    agent.note_spoken("Bonjour")

    assert asyncio.run(agent.forward_last_message_to_salon()) == "not_available"


def test_the_last_message_is_reported_to_the_journal():
    agent = salon.SalonAgent(follow_journal=True)
    link = _FakeLink()
    agent.set_journal_link(link)
    agent.note_spoken("Bonjour tout le monde")

    result = asyncio.run(agent.forward_last_message_to_salon())

    assert result == "forwarded"
    assert link.reported == ["Bonjour tout le monde"]


def test_only_the_most_recent_message_is_forwarded():
    """Every assistant turn overwrites this, so an old line never resurfaces once a newer
    one has been said."""
    agent = salon.SalonAgent(follow_journal=True)
    link = _FakeLink()
    agent.set_journal_link(link)
    agent.note_spoken("first")
    agent.note_spoken("second")

    asyncio.run(agent.forward_last_message_to_salon())

    assert link.reported == ["second"]


def test_a_report_that_lands_nowhere_is_not_claimed_as_forwarded():
    """`report()` returning zero means nobody's journal actually recorded it — the same
    silent-failure case `OrchestratorLink` documents for an unreachable orchestrator."""
    agent = salon.SalonAgent(follow_journal=True)
    agent.set_journal_link(_FakeLink(recorded=0))
    agent.note_spoken("Bonjour")

    assert asyncio.run(agent.forward_last_message_to_salon()) == "not_available"
