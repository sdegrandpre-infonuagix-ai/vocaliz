"""
Salon – LiveKit Agent Worker
Entry point for the xAI-powered voice discussion agent.
"""

import logging
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import xai, silero, turn_detector

load_dotenv()
logger = logging.getLogger("salon-agent")


class SalonAgent(Agent):
    """Voice discussion agent powered by xAI Grok."""

    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are Salon, a sophisticated voice discussion facilitator. "
                "Your role is to animate intellectually stimulating conversations "
                "between participants about documents, articles, or current events. "
                "Speak naturally without requiring a wake word. "
                "Read source content aloud, ask engaging questions, introduce "
                "contrasting perspectives from other sources, and translate between "
                "languages when participants speak different languages. "
                "Intervene at most once per minute when participants share the same "
                "language, more frequently when actively translating. "
                "End sessions gracefully and ask a satisfaction question when a "
                "participant says they want to leave."
            ),
        )


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()

    session = AgentSession(
        llm=xai.realtime.RealtimeModel(voice="Ara"),
        vad=silero.VAD.load(),
        turn_detector=turn_detector.EOUModel(),
    )

    await session.start(
        room=ctx.room,
        agent=SalonAgent(),
        room_input_options=RoomInputOptions(),
    )


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(entrypoint_fnc=entrypoint)
    )
