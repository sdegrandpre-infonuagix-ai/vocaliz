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
| `InterpreteBase` | Transcribe, render, synthesise. Three collaborators and a text step between them, so it can fail in three places the other cannot. Cheaper, a little slower, and answered in a synthetic voice — which is the whole of what the tier gives up. |

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

## Who is speaking

The topology took a signal away and this gives it back. Nobody hears anybody else's voice,
so the cue that normally announces a new person — an unfamiliar voice — does not exist.
Everything arrives in the same synthetic voice as everything else, and without this a Salon
of three sounds exactly like a Salon of two.

Each listener is told once, per person, immediately *before* that person's first message
reaches them. Before, not after: knowing who spoke matters most while you are hearing what
they said. A long intervention cut into pieces (Story 6.5) is still one person starting to
speak, so it is introduced once.

Somebody arriving into a conversation already under way is told who has spoken so far, in
their own language. Only who has *spoken*: a participant who has said nothing has no
detected language, and no language is ever invented. When several people already heard
share one language and it is the newcomer's too, that is said once instead of being spelled
out per person.

Names come from `Participant.name` — a registered user's, or the one the host spoke at the
invitation. Never a telephone number and never an internal identifier: a caller is
identified by the number they dialled from, and reading it out publishes it to the room.
`display_name` falls back to a neutral designation instead.

Attribution outlives the seat. Somebody who left is still the author of what they said, so
a late arrival given the history hears their words *and* hears whose they are.

## Cutting a microphone

`Salon.mute` / `Salon.unmute`, host only — `NotTheHost` otherwise, and a Salon with no
declared host lets nobody do it, because the alternative default is everybody.

Story 6.6 removed every notion of being granted the floor. This is the one asymmetry left
in a Salon, and it is deliberately blunt: it stops one participant being heard and does
nothing else. They stay in the Salon, keep their room and their position, and go on hearing
everybody — which is the whole difference between this and removing them. What they said
before stays in the journal; a cut is not a way to unsay something.

A cut interpreter is not even asked what it heard. Transcription is billed by the minute
and somebody who has been silenced should not go on paying for it.

Both notices are spoken in the participant's own language (`notices.py`, written out rather
than translated at runtime). The cut notice says they can still hear, because that is the
part they cannot verify: silence from a microphone is indistinguishable from a broken
interpreter, and the person it happened to is least able to tell which. The restore notice
matters for the same reason in reverse — otherwise their first sentence is spent testing
whether anyone can hear them.

The notice goes through `announce`, so Story 6.5's rule holds: it waits for the end of an
intervention rather than landing in the seam. And it is a courtesy, not the mechanism — an
interpreter too broken to say it does not leave the microphone open.

When the microphone comes back, nothing is owed for the silence. The next thing they say
takes the next position in the journal, behind whoever spoke while they were quiet.

## Introducing people

The topology takes away the two things that normally tell you who is talking: nobody hears
anybody's real voice, and everything arrives in the listener's own language. Without an
introduction a Salon is a series of sentences from nowhere.

The trigger is the first thing somebody actually **says**, not their arrival. A language is
detected, never declared — introducing somebody earlier would mean inventing a language for
them or introducing them twice. Somebody who stays silent all Salon is never mentioned, and
a switch of language later does not revise the introduction: "Marie now speaks English"
mid-conversation is noise, not information.

The introduction is spoken immediately before that speaker's first message, in the
listener's own language, naming the speaker's. Once per listener — an introduction repeated
is an introduction that stops being heard — which is why the state lives on the `Seat`
rather than the Salon: two people who joined at different moments have heard different
things.

Somebody arriving mid-conversation is told who has already spoken, in one announcement,
read from the journal (so it survives a takeover, and so somebody who has since left is
still named in the words of theirs the arrival is about to hear). When everybody already
heard shares the **arrival's own** language, that is said once instead of enumerated —
though only then: "everyone here speaks French" tells a German speaker nothing they needed.

Names come from the participant, and there is a neutral designation when there is none.
That is the ordinary case for a telephone participant (FR57), and precisely the case where
the obvious fallback would be to read out their number.

## Giving a late arrival the history

Three decisions, and they are genuinely separate.

**Whether** somebody gets it is the host's, taken in the same breath as the invitation —
"invite Marie, with the history" or "without". `history_from_invitation` reads it out of
what was actually said, in whichever language the host said it in. Refusals are matched
before grants, and that ordering is the whole subtlety: "sans l'historique" contains
"l'historique", so the other order would turn every refusal into permission.

Saying nothing is **not** a refusal. It falls to `DEFAULT_HISTORY_FOR_ARRIVALS`, which
grants: somebody invited into a conversation is being invited into what it has been about,
and a host who wants otherwise says so. This reversed the Story 6.4 default.

**Where** that puts their position needs no mechanism of its own — zero or the head, and
the ordinary rules do the rest.

**Whether it is replayed or summarised** is decided by volume and nothing else. Below
`condensation_threshold_seconds` the backlog is replayed message by message; above it, the
interval is said in substance. A Salon two minutes old is replayed in full however it was
granted; a listener twenty minutes behind is summarised however they got there. Anything
arriving during the catch-up is no special case — the next delivery weighs the same
threshold against whatever has accumulated since.

Everybody already in the room is told when an arrival is granted the history. What they
said before this person existed to them is about to be said to that person, there is no
taking it back, and the only honest moment to say so is before it happens. Nothing is said
when the journal is empty: granting access to nothing discloses nothing.

## Cleaning, and the pause marker

`src/journal/cleaning.py`. Hesitation is removed **at ingestion**, once, so N listeners
share one cleaning rather than each paying for their own — and so every lag downstream is
measured on what is actually left to say. Cleaning a Salon's speech shortens every room's
backlog at the same moment.

The line it must not cross is the one between cleaning and condensing (FR53). Hesitation
goes; not one word carrying meaning does. Two places that shows in the rules:

- Fillers are matched whole. `heureux` begins with `heu`, and deleting a word for looking
  like a noise is exactly the failure this exists to avoid.
- A stammer is collapsed only for words of three letters or fewer. People stammer on
  function words; repeating a longer one is usually deliberate, and `très très bien` means
  something `très bien` does not. The asymmetry decides it — missing a stammer costs a
  repeated syllable, deleting an intended word costs a meaning in a language the listener
  cannot check.

A silence under `SIGNIFICANT_PAUSE_MS` (2 000) is breathing and goes with the rest. Above
it, it was carrying something, so it survives as `[pause=N]`, capped at `MAX_PAUSE_MS`
(5 000) — reproducing thirty seconds faithfully would reproduce the moment everybody
assumed the call had dropped.

The marker is metadata, and four rules follow from that. It is **never pronounced**
(`Utterance.spoken_text` strips it at the last moment; the duration travels separately as
an indication of intent, applied idiomatically). It is **not content** — `spoken_length`
ignores it, so Story 6.5 never cuts an intervention short for a reason nobody could hear.
It **counts in full against a lag**, because the silence occupies real time when played.
And it is **dropped by a condensation**: one does not summarise silences.

Nobody can inject one by saying it. `neutralise` defangs anything of the form `[key=value]`
that came out of a human's mouth — matched on the shape rather than on the word `pause`, so
the emphasis and tone markers the story promises later are not injectable from the day they
ship.

## Which languages are offered

`offered_languages` takes the **intersection** of what the adapters speak, never their
union. Speech-to-speech is the most restrictive, so speech-to-speech decides.

The rule is commercial before it is technical. A language only the Base stack handles would
work perfectly until the customer upgraded, and would then vanish — at the exact moment
they started paying more. Refusing it up front costs a language nobody had yet; offering it
costs a customer, at the worst possible moment. The corollary is what makes tiers usable at
all: the offer is a subset of every adapter, so changing tier — mid-Salon or between Salons
— never changes what somebody can be spoken to in.

The orchestrator is never told which tier anybody is on. That is not an omission: `Salon`
has no parameter that could carry the answer, and `test_mixed_tiers.py` asserts it.

## Who speaks when

Nobody is given the floor. There is no turn, no request to speak and no allocation by the
agent — FR9 is not unimplemented, it is removed — and `test_arrival_order.py` asserts that
no method on `Salon` could hand somebody the right to speak.

The order of the journal *is* the order of arrival, because positions are assigned
monotonically as messages arrive. No second structure is kept in step with it, and reading
follows the positions rather than the clock: NTP moves a drifting clock backwards, and what
was already said must not become something said later.

`arrival_key` is for comparing messages that did not come from the same journal — the
arrival timestamp decides, and the position settles ties. There are plenty of those: a
clock has finite resolution, two rooms can hand over inside the same microsecond, and the
pieces of one split intervention deliberately share a single instant.

Positions are assigned before the first `await`, so two arrivals genuinely in flight
together cannot land on the same one, and two long interventions arriving at once still
occupy two unbroken stretches.

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
