"""Driving each adapter of the Interpreter port through the same contract tests.

An adapter is fed and inspected differently depending on what sits behind it — a queue for
`InterpreteFake`, a stubbed realtime session for `InterpreteS2S` — but what the contract
asks of them is identical. The harness is where that difference is absorbed, so the
contract tests themselves never mention one adapter or the other, and no production class
grows a hook that exists only for a test.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.interprete import Interprete, InterpreteFake, InterpreteS2S, Participant, Utterance


@dataclass
class StubRealtimeSession:
    """A realtime audio↔audio session that never leaves the process.

    Stands in for the provider's model. Instructions in, what the human said out — which is
    the whole surface `InterpreteS2S` is allowed to use, and the reason the adapter can be
    tested without a vendor SDK or a network.
    """

    heard: list[tuple[str, str]] = field(default_factory=list)
    spoken: list[Utterance] = field(default_factory=list)
    unsupported: set[str] = field(default_factory=set)
    closed: bool = False
    fail_with: Exception | None = None
    closes: int = 0

    def supports(self, language: str) -> bool:
        return language not in self.unsupported

    async def listen(self) -> tuple[str, str] | None:
        if self.fail_with is not None:
            raise self.fail_with
        if self.closed or not self.heard:
            return None
        return self.heard.pop(0)

    async def speak(self, utterance: Utterance) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.spoken.append(utterance)

    async def aclose(self) -> None:
        self.closes += 1
        self.closed = True


@dataclass
class RecordingVoice:
    """A voice that does not go through the provider.

    NFR3 asks that a participant be told out loud when their interpreter cannot answer —
    which cannot be done with the very model that has just stopped answering. This stands
    in for whatever independent voice the room ends up using.
    """

    said: list[tuple[str, str]] = field(default_factory=list)
    fail_with: Exception | None = None

    async def __call__(self, text: str, language: str) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.said.append((text, language))


class Harness:
    """What a contract test may do to an interpreter, whichever adapter it is."""

    interprete: Interprete
    voice: RecordingVoice

    def hears(self, text: str, language: str) -> None:
        raise NotImplementedError

    def close_room(self) -> None:
        raise NotImplementedError

    def refuse_language(self, language: str) -> None:
        raise NotImplementedError

    def fail_the_provider(self, error: Exception) -> None:
        raise NotImplementedError

    @property
    def _spoken(self) -> list[Utterance]:
        raise NotImplementedError

    @property
    def spoken(self) -> list[str]:
        return [utterance.text for utterance in self._spoken]

    @property
    def spoken_languages(self) -> list[str]:
        return [utterance.language for utterance in self._spoken]

    @property
    def verbatim(self) -> list[bool]:
        return [utterance.verbatim for utterance in self._spoken]

    @property
    def kinds(self) -> list[str]:
        return [utterance.kind for utterance in self._spoken]


class FakeHarness(Harness):
    def __init__(self, participant: Participant) -> None:
        self.voice = RecordingVoice()
        self.interprete = InterpreteFake(participant=participant, fallback_voice=self.voice)

    def hears(self, text: str, language: str) -> None:
        self.interprete.queue(text, language=language)

    def close_room(self) -> None:
        self.interprete.close_room()

    def refuse_language(self, language: str) -> None:
        self.interprete.unsupported.add(language)

    def fail_the_provider(self, error: Exception) -> None:
        self.interprete.fail_with = error

    @property
    def _spoken(self) -> list[Utterance]:
        return self.interprete.spoken


class S2SHarness(Harness):
    def __init__(self, participant: Participant) -> None:
        self.voice = RecordingVoice()
        self.session = StubRealtimeSession()
        self.interprete = InterpreteS2S(
            participant=participant, session=self.session, fallback_voice=self.voice
        )

    def hears(self, text: str, language: str) -> None:
        self.session.heard.append((text, language))

    def close_room(self) -> None:
        self.session.closed = True

    def refuse_language(self, language: str) -> None:
        self.session.unsupported.add(language)

    def fail_the_provider(self, error: Exception) -> None:
        self.session.fail_with = error

    @property
    def _spoken(self) -> list[Utterance]:
        return self.session.spoken
