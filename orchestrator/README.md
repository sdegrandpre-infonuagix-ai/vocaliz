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

## Falling behind, and being caught up

`Salon._condense_if_far_behind`. The lag is `head − cursor_i`, measured in seconds of
*content* rather than of clock, and it belongs to one interpreter. Past
`condensation_threshold_seconds` the backlog is said in substance instead of replayed, the
cursor jumps to the end of what was summarised, and the lag collapses — catching up faster
than real time is the only way a reader who has fallen behind ever gets back.

It is not a mode. Nothing switches condensation on or off: each delivery weighs the same
threshold against whatever has accumulated, so full message-by-message rendering resumes by
itself the moment the lag is down. There is no state to get stuck in.

Because the journal is not a queue and reading consumes nothing, one interpreter racing
through a summary takes nothing from anybody. Another participant's cursor does not move,
the journal is not edited, and somebody equally far behind is condensed on their own
account, from their own position, because of their own lag.

Two details are less obvious than the threshold:

- **It is announced first.** `condensed_while_listening` says how many people spoke before
  the gist arrives. Without it a summary is indistinguishable from the conversation having
  been quiet — the listener gets less than everybody else and has no way of knowing. Said
  afterwards it would explain something they have already had to make sense of unaided.
  The count is of *people*, not messages: somebody who spoke four times is one person to
  catch up on. There are separate singular and plural sentences per language, because a
  number glued onto a stem reads as machine-written in all six.
- **Nobody is summarised about their own words.** A long speaker puts themselves behind by
  exactly the amount they just said, so without excluding their own entries they would be
  told that one person spoke while they were listening, and handed the gist of themselves.

Failing to speak the announcement never costs the summary it introduces, the same rule
introductions follow.

## Mixed modes, and changing one mid-Salon

`Salon.change_mode`. Three participants on three different tiers are not a case the conductor
handles — they are the case it cannot tell apart. It only ever talks to the `Interprete`
port, so a dearer adapter is the same code path holding a different object, and a test reads
`conductor.py` looking for `isinstance` or an adapter class name to keep it that way. No tier
can acquire a special case by accident.

A mode persists because nothing changes it. The only thing that does is the participant, and
when they do, everything around the adapter stays exactly where it was: the same room, so
nobody is put through a reconnection; the same reading position, so nothing is replayed; the
same record of who they have been introduced to, since that belongs to the listener rather
than to the adapter.

The reading position is the one worth being careful about. A swap that reset it would replay
the whole conversation from the beginning — a considerably worse outcome than the wrong voice
for a minute. The outgoing adapter is closed, because it holds a provider session and leaving
it open keeps paying for a room nobody is listening to.

## The order the interpreter speaks in

`src/salon/meta_speech.py`. The problem is reproducibility rather than fairness. Several
things can become ready during one long intervention, and if the order they emerge in depends
on which coroutine happened to resume first, the same scenario produces different audio twice
and no test can pin any of it down. So the order is a property of the queue and never of the
event loop.

| Rank | What |
|---|---|
| 1 | `BUSY` — "Vocaliz is busy" (FR49) and the request to top up (FR56) |
| 2 | `BALANCE` — a low balance, and the Salon about to end (FR55) |
| 3 | `NOTICE` — arrivals, microphone changes, the ordinary facts of the conversation |
| 4 | `ADVERT` — advertising (FR39) |

The specification names ranks 1, 2 and 4 in that order. `NOTICE` is not in its list, and
sitting it between the balance alerts and the advertising is the reading that keeps the three
named ranks in exactly the given order while refusing to let anything being *sold* precede a
fact about the conversation itself.

**It sequences; it does not arbitrate.** `drain()` returns everything waiting, not the most
urgent one — a slot between two messages is the chance to say what is owed, and keeping the
rest back for a later slot is precisely how the least urgent thing ends up never being said.
Nothing is dropped, deduplicated or replaced either: two identical sentences are two things
that happened.

Within a rank the tie is broken by an arrival counter rather than a timestamp or object
identity. Two things ready at the same instant need a settled order, and a clock can tie
while a counter cannot.

Two kinds of speech stay outside this on purpose. A participant's introduction and their
history are said as they enter the room, before they are in the conversation at all. And the
sentence announcing a condensation belongs to the summary it introduces — ordering it
separately would strand "while you were listening, three people spoke" next to something
else entirely.

## Simulated participants, and what a run is judged by

`src/load/`. The purpose is a decision: raising the participant ceiling from 3 to 50 is
either a measurement or a bet, and the only way to make it a measurement is to run 50
participants without paying a provider for any of them.

`SimulatedSpeaker` is what `InterpreteFake` was not. The fake is *reactive* — you queue what
its human says. A scenario needs something that decides on its own when to speak and what to
say, at a cadence, a length and a language somebody chose. It is deterministic on purpose:
same seed, same words, same verdict, because a load result that changes between runs is
measuring the generator. It is seeded on the participant as well as the run, so fifty
speakers do not all say the same sentence and leave the translation cache doing the work.

`scenario.run` plays a whole scenario against a **real** Salon — the real journal, the real
cursors, the real condensation and saturation rules. Only the humans and the interpreters are
simulated; replacing the conductor would measure the harness. Scenario time is not wall-clock
time, so an hour-long run finishes in milliseconds and can live in the test suite.

Two things in the harness are less obvious than they look:

- **Interpreters have a budget.** `render_speed` says how fast one renders as a multiple of
  real time. Without it every interpreter drains its backlog instantly, nobody can fall
  behind, and the harness can only ever confirm that everything is fine.
- **Summarising is not free.** An interpreter with no time renders nothing at all,
  condensations included. Treating condensation as free lets every room rescue itself on
  every step — and since the settings guarantee condensation fires before saturation, no
  scenario could then ever reach a block.

`SalonMetrics` holds what a run is judged by: the lag of each cursor kept at its *peak*
rather than its last value — a lag sampled after a delivery reads as zero exactly when
somebody was furthest behind — the worst lag in the Salon, latency at p50 and p95, the share
of content summarised, and blocks both counted and timed. A block still open when the run
ends is charged up to the end, because "blocked and never released" is the one result nobody
should be able to report as zero blocked time.

The **meta-speech ratio** is how much of what somebody hears was said by nobody in the room:
the tax the architecture charges for existing. Condensed content is left out of both sides —
it is neither the journal spoken faithfully nor the system talking about itself — while the
sentence that *announces* a condensation counts, because that is precisely the interruption
the ratio exists to make visible. It is published per tier, since the cheapest tier
interrupts most and one averaged number would hide exactly that trade. A tier that never ran
reports `None` rather than zero: a missing row reads as "no interruptions" when it means
"never ran", and those are opposite conclusions.

`Report.of` gives the verdict against the four criteria for raising the ceiling, and **fails
closed on every one**. A run that did not measure something has not met it: no cost figures
supplied is not the cost criterion met, and zero blocks in ten minutes is not an hour without
one. Scaling the requirement to the run length would turn a short run into a free pass.

## Cohorts, and what they are allowed to be compared to

`src/cohorts.py`. Two numbers that are easy to publish in a way that misleads.

The conversion rate — what share of a cohort recharged before their 30-day credit expired —
only means anything once that cohort's window has closed. A cohort three days old has had
three days and will look catastrophic beside one that had a month. So a partial cohort is
marked partial and `compare` **raises** rather than warning: a caveat printed next to a
number is read by nobody, and the number is what gets quoted.

The delay to first payment is published as a distribution — median, p25, p75, p90 — and never
as a mean, because one person who came back on day 29 drags an average past usefulness.
Somebody who never recharged is counted against the rate and left out of the delay: they have
no delay, and counting them as a large one invents a number while counting them as zero
invents a better one.

A declined card is a bank's decision and not a person's, so the delay runs to the first
*success* and failures are counted separately. Folding them together would read a payment
problem as a lack of interest.

## The monologue ceiling

`Salon._may_interrupt`. Story 6.5 established that nothing third-party is spoken inside
somebody's intervention: a long one is cut into consecutive messages, and slipping an
announcement between two of them leaves the listener with half a sentence, an unrelated
notice, and the other half to reassemble themselves.

That rule is right and it has a limit. Held with no ceiling it becomes the means by which one
person makes everybody else unreachable — nothing can be said to anybody for as long as they
keep talking. Past `monologue_ceiling_seconds` the protection is withdrawn and insertion is
allowed inside the run.

It is a choice between two costs, and the ceiling is where they cross. Under it, cutting a
thought costs more than a delayed announcement. Over it, the delay has stopped being a
courtesy to the speaker and become a silence imposed on everybody by one of them, which a
clipped sentence is cheaper than.

The count is per *run*, in seconds of content, and resets at every seam — somebody who spoke
at length, stopped, and started again has yielded the floor in between, so the protection is
theirs once more. Measuring content rather than messages keeps the ceiling from depending on
where the splitter happened to cut.

`monologue_ceiling_seconds` starts at 300, the same number as `saturation_threshold_seconds`,
and that is a coincidence of judgement rather than a relationship. They answer different
questions — how long one person may hold the floor, and how far behind a room may fall — and
there is deliberately no ordering rule between them: neither silently disables the other, so
a rule would only refuse configurations that work.

## Saturation, and the alarm

`Salon._review_saturation`. When one room's own lag passes `saturation_threshold_seconds`
that room says **"Vocaliz is busy"** to its single participant and stops accepting anything
they say, until the lag falls back under `unblock_threshold_seconds`.

This is the alarm, not the first resort. Condensation runs continuously and per room, so a
room that saturates *despite* it is one whose regulation has run out — the lag survived being
summarised. That ordering is not a convention: `SalonSettings` refuses a configuration where
condensation does not sit strictly below saturation, which is what makes this signal worth
believing when it arrives.

Everything here belongs to one room and never to the Salon. One interpreter falling five
minutes behind says nothing about anybody else's, so a mixed state — one room blocked, the
others untouched — is the expected condition rather than a degraded one.

What blocking stops is **ingestion only**. A blocked participant keeps hearing everybody,
which is the point: they are behind, so cutting delivery would take away the very thing they
are short of. And they are told the moment they speak, rather than having their words
dropped in silence and finding out much later, if at all.

Three details:

- **The lag counted is what they have not *heard*.** Their own words are never rendered back
  to them, so counting the raw lag would have a long speaker saturate their own room by
  talking and then be blocked for it.
- **A thought is never cut in half.** The decision is taken before an intervention starts,
  and `record_intervention` cuts and appends the whole thing in one go — so an intervention
  long enough to cause the block cannot have its own tail refused by it.
- **The signal is spoken on the crossing, once.** Repeating it per message would bury the
  conversation the participant is already struggling to follow. Reopening is not announced
  at all: being able to speak again is discovered by speaking, and a notice would interrupt
  the conversation to report that nothing is wrong.

"Vocaliz is busy" stays in English in all six languages — it is the product saying its own
name, and translating a brand gives somebody six different things to search for when they
want to report the problem. The rest of the sentence is theirs; three English words alone
tell a German reader nothing. If the adapter cannot speak the alarm the room is blocked
anyway: the block is about the lag, not about whether the sentence was delivered.

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

## Nothing said reaches a log

Encryption at rest was already delivered by the Aurora cluster's KMS key, which covers the
storage, the snapshots and the backups together — the journal, the cursors and the
translations all live there. A column-level scheme would have forced a deterministic cipher
on the key columns and ruled out every query but equality, and it would have missed the
backups entirely.

The half that needed work is the easy one to break by accident: **a diagnostic line that
echoes a message body puts in clear, in CloudWatch, exactly what the database is
encrypting.** Two guards, because either alone is weak.

A **static** one fails the build when a logging call is handed anything content-shaped —
`.text`, `words`, `transcript`, `heard`. Cheap, and it catches the mistake in the diff
rather than six months later. It also refuses a bare `logging.info(...)`, which would write
to a root logger nothing here configures.

A **live** one runs a whole three-language Salon — introductions, a condensation, a
microphone cut, a provider failure — with every logger at DEBUG, and asserts that not one
word anybody said appears anywhere in the output. Translations count: derived from what
somebody said makes them exactly as private as the original. So do pause markers, since how
long somebody hesitated is a fact about them even though it is not a word.

`logging_config.about(entry)` is the right way to say a message went wrong: identifiers and
lengths, and the length is of the speech alone. The wrong way is one f-string away, which is
why the right one is worth keeping close at hand.

## Video, muted

`src/salon/video.py`. It exists because the topology took something away: nobody hears
anybody's real voice any more, so the oldest proof of identity there is — recognising
somebody by how they sound — is gone. Seeing them gives it back, and that is the entire job.

Everything else follows from it being the *only* job:

- **No sound.** `VideoTrack.audio` is a field rather than an omission, so the promise is
  visible in the data. A second sound channel would be a second way for two humans to hear
  each other, and the absence of that is what makes echo unavailable rather than cancelled.
- **A separate path.** `VideoPath` is not `RoomProvisioner`, and track names carry a
  `video--` prefix so the two paths are distinguishable at a glance. Derived, like room
  names, so a takeover can name them again from what it re-read.
- **Never kept.** There is no method on the port that could retain a frame — which is how
  "never recorded" is stated in a way that cannot rot. NFR8 does not reach it: the text
  journal is what a takeover needs and what proves an advertisement was broadcast.
- **A vignette.** 240p at 15 fps under an explicit 200 kbps cap, never the SDK default,
  which climbs to 720p and costs about 15% of the Base tier instead of about 2% — for no
  gain at all in answering "is that the person I think it is".

Off until somebody asks. A camera that comes on by itself is a camera nobody consented to.
Driving mode (FR75) suspends it both ways and **remembers the wish**: somebody whose camera
was on before the drive did not choose to turn it off, and somebody who never turned it on
does not find it running afterwards. `shed_video` drops pictures to save the conversation —
always in that order, because a conversation without pictures is still a conversation.

A telephone participant (FR57) has no video either way, and the others are told. Without
that, their empty tile reads as somebody who chose not to be seen, which is a different
thing and invites a judgement they have not earned.

The layer is optional: a Salon built without a `VideoPath` loses the pictures and nothing
else.

## Captions

`src/salon/captions.py`. Not a lesser copy of the voice — they reach further. Text renders
into languages no realtime model can pronounce, so somebody can follow a Salon in a language
they could never be spoken to in. `caption_languages()` is deliberately a superset of
`captions_offered_in()`, which stays the intersection of the adapters from Story 6.7: being
able to *read* Welsh is not being able to be *spoken to* in it, and a participant reading a
language no adapter speaks has their voice fall back while their captions do not.

Three states, and the middle one is easy to lose:

| `caption_language` | Meaning |
|---|---|
| `None` | Never chosen. Off because nobody has been asked. |
| `""` (`AS_SPOKEN`) | Chosen: show the original, translate nothing. |
| a language | Chosen: render every turn into it. |

Each reader chooses independently, and the size (`caption_scale`) follows the account rather
than the device — somebody who needs larger text needs it on their telephone too.

Translation is the one the voice already pays for: `SalonLog.render` against a cache keyed
on (turn, language), so a turn read by three people in German costs one translation, and
every caption is one hop from the original rather than a translation of a translation. A
turn already in the reading language is shown as spoken, and leaves no translation row.

Captions travel the data channel of the reader's **own room** and nowhere else — the same
isolation that makes echo impossible. They are never handed to the voice: a caption is
something to read, and sending it to the interpreter would say everything twice. Pause
markers are stripped, because there is nothing to read in a silence.

## The speaking indicator

`src/salon/speaking.py`. The signal this replaces is the one the topology destroyed:
silence in your ear used to mean nobody was speaking, and now it means your interpreter has
nothing to render yet. From the inside those are indistinguishable.

So each pair carries **two** lights rather than one. Somebody speaking and their interpreter
rendering are different facts, and the second explains the delay in the first — seeing Marie
green and her interpreter still red is seeing exactly why you are still waiting. One light
would collapse the two and lose the explanation.

Nothing here detects anything. LiveKit publishes speaking state natively and the Silero VAD
is already in `livekit-agents[silero]`; what is missing is only that a room's state stops at
the room, and the humans share none. This is the carrying, over the same data channel as the
turns and the captions.

`Voice` carries a **colour and a shape**. UX-DR7 asks that colour never be the only carrier:
somebody who cannot tell green from red still has to be able to read the board, and it has
to survive being printed in black and white.

`SpeakingBoard.set` returns whether anything actually moved, and that return value is the
whole economy of the feature — Silero reports continuously, and rebroadcasting an unchanged
board to everybody many times a second would be the most expensive possible way to say
nothing. Nothing is sent to a screen that is black in driving mode either.

## The Salon's parameters

`src/settings/`. Deliberately not `src/config.py`, and the split is about what changing a
value should cost. A credential belongs in the environment: it is set once, it is secret,
and changing it *should* mean a deploy. A threshold does not. `condensation_threshold_seconds`
is a number somebody will want to move while a Salon is going badly, and putting a tuning
knob behind a deployment means in practice it never gets turned.

So these live in a table, are read at startup, and reach a running fleet without a restart.
`LiveSettings.get()` is a coroutine rather than an attribute for exactly that reason: several
instances serve one Salon and the only thing they share is the table, so each re-reads it
every `DEFAULT_RELOAD_SECONDS` (30). Reading on every access would make this the busiest
query in the system; never re-reading would make a change a deploy, which is the thing FR54
exists to avoid.

| Parameter | Starts at | What it governs |
|---|---|---|
| `condensation_threshold_seconds` | 120 | Above this lag an interpreter condenses (FR53) |
| `saturation_threshold_seconds` | 300 | Above this a room signals and stops accepting (FR55) |
| `unblock_threshold_seconds` | 240 | And below this it is let go again |
| `max_message_characters` | 500 | Where a long intervention is cut |
| `significant_pause_ms` | 2000 | Above this a silence is content, not breathing |
| `max_pause_ms` | 5000 | The longest pause ever reported |

Two of the rules between them look like ordinary validation and are not. Condensation at or
above saturation would mean condensation never once ran before the alarm it exists to
prevent; unblocking at or above saturation would mean a room unblocked straight back into
the condition that blocked it. Neither mistake raises anything anywhere — the system simply
stops doing something it was built to do, silently, for as long as nobody looks. Refusing the
configuration is the only moment either is visible, so the refusal names the fields, the
values *and* the consequence.

A change is validated against the values it lands beside rather than on its own: 250 is a
perfectly good condensation threshold and wrong next to a saturation threshold of 200. It is
refused before it is written, because a bad edit that was correctly refused here would
otherwise still be sitting in the table to fail the next instance on the way up.

The table is key/value rather than a row of typed columns, so adding a parameter is not a
migration. The cost is that one numeric column holds everything, which is why `SalonSettings`
puts the integer types back on the way out — `max_message_characters` slices text and cannot
arrive as `400.0`. A stored name the dataclass does not know is refused rather than dropped:
a row left behind by a removed parameter should be loud, and a typo that appeared to save and
did nothing is the least debuggable outcome available.

## Driving mode

`Salon.start_driving` / `stop_driving`. The screen goes black and *replaces* the room rather
than dimming part of it, so everything that exists only to be looked at stops at once: the
video both ways, the captions, and the speaking board. The conversation itself is untouched.
Somebody driving still hears every turn, still speaks, and is still told when somebody
joins — announcements are spoken, and a black screen is no reason to stop hearing them.

Of the three, the captions are the one with a price on them. A translation is billed per
turn, so leaving the language set would buy text for a screen nobody is looking at.
`start_driving` empties `caption_language`, which is enough on its own: `_send_caption`
already gates on it, so nothing is rendered and nothing is published.

Both suspensions are restored on the way out, because they did not choose to stop reading or
to turn the camera off — they chose to start driving. Two details make the restore correct
rather than approximately correct:

- Starting twice must not save the emptied state over the real one, so the previous choice
  is put aside only on the transition into the mode.
- A choice made *during* the drive wins. Somebody who reaches for the setting at a red light
  meant it, so `set_captions` drops what was put aside; restoring the older value would
  overwrite a decision with the one it replaced.

`""` (`AS_SPOKEN`) has to come back as `""` and not as `None` — the difference between
"show me the original" and "never chosen" is exactly the difference between captions on and
captions off, which is why the seat remembers a `(language, scale)` pair and not a language.

The black screen itself, the wake lock that keeps the phone from locking after 30 seconds,
the whole-surface exit target and the separate hang-up target low where the thumb rests all
belong to the client and live in `mobile/src/components/DrivingMode.tsx`.

A telephone participant (FR57) gets the same two lights as everybody. With no video, it is
the only visual information about them there is, which makes leaving them off the board the
one thing that would actually hurt.

A board is JSON with a `kind`; a caption is the text itself. Both travel the same channel,
so a client can tell them apart without guessing.

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
