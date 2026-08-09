# Salon Orchestrator

The central component of the multi-rooms topology (Epic 6). One LiveKit room per
participant, one interpreter per room, and this service in the middle.

Story 6.1 delivers the service itself and nothing that runs on it: it starts, reads its
configuration, journals its start, answers two health probes and drains on SIGTERM. The
journal and the interpreter reading positions arrive in Story 6.3, the rooms in 6.4.

It is a **new deployable, separate from the interpreter worker** in `agent/`. The worker
stays where it is and becomes the host of the Interpreter port adapters in Story 6.2 —
this service is added beside it, never in its place.

## Run it locally

No AWS account, no LiveKit subscription, no paid provider — the stories that follow have
to be developable offline.

```bash
cd orchestrator
uv sync --all-groups
cp .env.example .env
uv run uvicorn src.main:app --reload --port 8080

curl localhost:8080/health         # liveness
curl localhost:8080/health/ready   # readiness
```

## Tests

```bash
uv run pytest -q
```

## The Interpreter port

`src/interprete/` — one interpreter per participant, and the only thing the orchestrator
is allowed to know about one. Four verbs: `ingest`, `render`, `insert_annonce`, `condense`.

| Adapter | Behind it |
|---------|-----------|
| `InterpreteS2S` | A realtime audio↔audio session. The human speaks, the model answers in voice; no text step inside the room, and a turn in another language is handed over whole for the model to render and speak in one movement. |
| `InterpreteFake` | A queue. Deterministic, in memory, no socket — what Story 7.2 verifies condensation against. |
| `InterpreteBase` | Story 6.7: STT + LLM + TTS, same contract, no change to the orchestrator. |

No provider SDK is imported anywhere under `src/` — `test_interprete_port.py` fails the
build if one ever is. The realtime session is supplied by whatever hosts the adapter (the
interpreter worker in `agent/`) and only has to answer the `RealtimeSession` shape.

Failures are typed: `ProviderUnavailable` and `UnsupportedLanguage`, both under
`InterpreteError`. When a provider stops answering, the participant is told out loud
through a fallback voice — never through the model that has just failed — and the
orchestrator gets the typed error regardless (NFR3).

## The journal

`src/journal/` — one `SalonLog` per Salon, which is what an instance holds and what
another instance can take over.

- **The journal** is append-only, numbered monotonically per Salon and stamped on arrival.
  It is the only structure of messages there is. Not a queue: a message is rendered once
  per participant, at a rhythm each interpreter sets for itself, so there is no point at
  which it has been consumed. Entries are frozen — the speaker makes the original.
- **The cursors** are the only thing that moves. One per reader, independent, never
  backwards. A reader's lag is the content between its position and the head, measured in
  seconds of content rather than of clock.
- **The translations** are keyed on (position, language) and shared by everybody listening
  in that language. A message already in the listener's language is never translated and
  leaves nothing behind; every translation is made from the original, never from another
  translation. A Salon held in one language never touches the translator at all.

Everything is written through a `JournalStore` as it happens, and `SalonLog.resume()`
rebuilds a Salon elsewhere with no loss and nothing said twice. `InMemoryJournalStore` is
for offline work; `SqlJournalStore` is the durable one (NFR8) — SQLAlchemy Core over three
tables the orchestrator owns, tested against SQLite so the suite needs no database, and run
against Postgres. The API's `utterances` tables are untouched: they serve a Salon's
transcript to a client, which is a different job.

## Rooms, and a Salon running

`src/salon/` — one room per participant, and the object that ties rooms, interpreters and
the journal together.

A `Room` holds exactly two occupants: one human and that human's interpreter. There is
never a second human in it, so there is no audio to leak from one person into another's
microphone and nothing for FR17 to cancel — **echo is unavailable rather than suppressed**.
Room names are derived (`{salon_id}--{participant_id}`) rather than random, so an instance
taking a Salon over can name the rooms again from what it re-read.

`Salon` (in `conductor.py`) keeps the two directions apart. `collect`/`ingest` is what comes
out of a room and into the journal; `deliver` is what goes from the journal back into one
room. Neither waits on the other — an interpreter that has fallen behind must not hold up
anybody else's words reaching the journal. Nobody is ever told what they themselves said,
and one interpreter failing costs its own participant a spoken apology (NFR3) and a position
that stays put, while every other room carries on.

The consequence worth stating: no participant ever hears another participant's voice.
Stories 6.13 and 6.15 — the muted video and the speaking indicator — exist to give back the
two signals this topology removes.

`InMemoryRoomProvisioner` is the offline implementation; the LiveKit one is built by the
interpreter worker, which is the only component with the SDK.

## Long interventions

`split_intervention` cuts anything over `MAX_MESSAGE_CHARACTERS` (500) into consecutive
messages. The number is not the point: the journal is read in order, so one enormous
message is a stretch during which nobody else can be heard by anybody.

Where the cut falls is the craft — a sentence boundary is where a listener expects a pause
anyway, so the seam is inaudible; between words when a sentence is itself too long; inside
a word never, except for a word longer than the whole maximum, where the alternative is
dropping it. `"..."` stays one hesitation and `3.5` stays one number.

The pieces take consecutive positions, assigned together with no `await` between them, so
no other participant's message can land in the middle. Each carries `part`/`parts` — and
those are persisted, because an instance taking the Salon over has to know it is part-way
through somebody's sentence. `Salon.announce` holds an announcement back while a listener
is mid-run and says it at the seam's end: an announcement dropped between two halves of a
sentence is worse than the same announcement a second later.

## Configuration

Everything comes from the environment; see `.env.example` for the full list and
`src/config.py` for the defaults.

`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` and `DATABASE_URL` have **no
defaults**. A missing one stops the process at startup with a message naming it — never
silently, and never on somebody's first Salon. In AWS they are not set by hand: the ECS
task passes `ORCHESTRATOR_SECRET_ARN` and the service reads the values from Secrets
Manager itself, exactly as the API does with `APP_SECRET_ARN`.

## Health

| Path | Question | While draining |
|------|----------|----------------|
| `/health` | Is the process wedged and worth killing? | `200` — a draining instance is alive and must not be killed |
| `/health/ready` | May this instance be given new Salons? | `503` |

The ECS container health check probes `/health` for exactly this reason: probing readiness
would have the platform kill a task in the middle of the Salons it is finishing.

## Deployment

AWS ECS Fargate, in the same account and network as the rest — no new platform to
administer.

- `Dockerfile` — the container image
- `ecs/task-definition.json` — hand-written, per the MVP decision not to use an
  infrastructure-as-code tool for this component. `${AWS_ACCOUNT_ID}`, `${ECR_REPOSITORY_URI}`
  and `${IMAGE_TAG}` are substituted by the pipeline; nothing else is generated.
- `.github/workflows/deploy.yml` — the same pipeline that deploys the API and the
  interpreter worker. One chain, one place to look.

A rolling deployment starts the new tasks, then sends SIGTERM to the old ones. Each drains:
it stops accepting Salons and waits `DRAIN_TIMEOUT_SECONDS` (90 s, under the Fargate
`stopTimeout` ceiling of 120 s) for the ones it holds.

Draining is a comfort, not a safety mechanism. The state of a Salon is persisted, so an
instance lost to a crash, an eviction or a failed health check costs an interrupted
experience and nothing else — another instance resumes from storage. Affinity between a
Salon and its instance stays worth having for latency; it is not a condition of survival.

## Logging

Identifiers and lengths, never text. No message, no summary, no fragment of a
transcription reaches CloudWatch or standard output — Story 6.12 makes it an acceptance
criterion, and it is the easiest one in the epic to break by accident.
