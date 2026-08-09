# Agent Build Instructions

## Project Structure

- `agent/` — Python LiveKit agent worker (xAI Grok, silero VAD, turn-detector)
- `api/` — FastAPI REST API (Lambda + API Gateway, deployed by the CDK stack in `infra/`)
- `orchestrator/` — Python orchestrator service (ECS Fargate) — Epic 6, multi-rooms topology
- `infra/` — AWS CDK (TypeScript), API stack only
- `mobile/` — Expo React Native app (iOS + Android)
- `.github/workflows/deploy.yml` — the one pipeline: tests on every push, deploys on
  `workflow_dispatch` with a component input (`api`, `agent`, `orchestrator`)

## Agent Worker (Python)

```bash
# Setup (one-time)
cd agent
uv sync

# Run locally (needs .env with LIVEKIT_URL, XAI_API_KEY)
cp .env.example .env
uv run python agent.py dev

# Run tests
uv run pytest

# Build Docker image
docker build -t salon-agent .
```

## Orchestrator (Python, ECS Fargate)

Separate deployable from the agent worker — it does not replace it. See
`orchestrator/README.md`.

```bash
# Setup (one-time)
cd orchestrator
uv sync --all-groups
cp .env.example .env          # starts with no AWS and no paid provider

# Run locally
uv run uvicorn src.main:app --reload --port 8080
curl localhost:8080/health          # liveness
curl localhost:8080/health/ready    # readiness (503 while draining)

# Run tests
uv run pytest -q

# Build Docker image
docker build -t salon-orchestrator .
```

`src/interprete/` holds the Interpreter port (`ingest`, `render`, `insert_annonce`,
`condense`) and its adapters — `InterpreteS2S` over a realtime audio↔audio session,
`InterpreteBase` over a transcribe-render-synthesise chain, `InterpreteFake` for
deterministic tests. `offered_languages` takes the intersection of what the adapters speak,
never their union — a language only one tier handles would vanish on an upgrade. No provider SDK is importable under `src/`, and
`tests/test_interprete_port.py` fails the build if one appears. New adapters are added to
the `ADAPTERS` list in that file, which runs the whole contract against them.

`src/journal/` holds one `SalonLog` per Salon: the journal (append-only, monotonic
sequence, stamped on arrival), one cursor per interpreter, and the translation cache keyed
on (sequence, language). Everything is written through a `JournalStore` as it happens;
`SalonLog.resume()` rebuilds a Salon on another instance. Two implementations:
`InMemoryJournalStore` for offline work, and `SqlJournalStore` (SQLAlchemy Core, three
tables the orchestrator owns) for durability. The SQL one is tested against SQLite, so the
suite still needs no database; Postgres is what it runs on.

`src/salon/` provisions one room per participant (`rooms.py`, one human + their interpreter,
never two humans) and holds the `Salon` that joins rooms to the journal (`conductor.py`):
`collect`/`ingest` for a room reaching the journal, `deliver`/`deliver_all` for the journal
reaching a room. `InMemoryRoomProvisioner` is the offline implementation; the LiveKit one
belongs to the interpreter worker, which is the only component with the SDK.

An intervention over `MAX_MESSAGE_CHARACTERS` (500) is cut by `split_intervention` into
consecutive journal messages on sentence boundaries, never mid-word. The pieces get their
positions in one go, so nothing lands between them, and `Salon.announce` holds an
announcement until a listener is out of a run.

`Salon.mute`/`unmute` (Story 6.8) are the host's only asymmetric power: `host_id` must be
set and must match `by`, or `NotTheHost` is raised. A cut stops ingestion and nothing else —
the participant keeps hearing everyone, and afterwards rejoins the arrival order with no
priority.

Introductions (Story 6.9) are spoken by each listener's own interpreter, once per person,
just before that person's first message — `notices.py` holds the copy, per language. A
newcomer is told who has already spoken; nobody silent is mentioned, and a telephone number
is never used as a name.

`Salon.join(..., history=)` (Story 6.10) takes the host's decision — `history_from_invitation`
parses it from the spoken invitation; saying nothing grants it. Above
`condensation_threshold_seconds` a backlog is condensed rather than replayed, and everybody
already present is told when an arrival is given the history.

`src/journal/cleaning.py` (Story 6.11) strips hesitation at ingestion — once, so every room
benefits — and turns a silence over `SIGNIFICANT_PAUSE_MS` into `[pause=N]`, capped at
`MAX_PAUSE_MS`. Markers are never pronounced (`Utterance.spoken_text`), never counted as
content (`spoken_length`), counted in full against a lag, dropped by a condensation, and
not injectable by saying one aloud (`neutralise`).

No conversation content reaches a log (Story 6.12). `tests/test_no_content_in_logs.py`
guards it twice — statically, by failing on a logging call handed anything content-shaped,
and live, by running a full Salon at DEBUG and asserting nothing said appears in the output.
`logging_config.about(entry)` is the sanctioned way to describe a message: identifiers and
lengths only.

`src/salon/video.py` (Story 6.13) is a media path separate from the interpretation rooms,
carrying no audio, capped at `MAX_VIDEO_BITRATE_KBPS` (200) / 240p / 15 fps, and with no
method that could record a frame. `Salon.enable_video`/`disable_video`/`start_driving`/
`shed_video` govern it; off by default, suspended while driving with the wish remembered,
and unavailable to a `by_telephone` participant, whose presence the others are told about.

`src/salon/captions.py` (Story 6.14): `caption_languages()` is wider than
`captions_offered_in()` — text reaches languages no voice pronounces. `Salon.set_captions`
takes `None` (never chosen), `""` (`AS_SPOKEN`) or a language, plus `caption_scale`.
Captions go out over the reader's own room via `rooms.publish`, never to the interpreter,
and reuse the journal's translation cache.

`src/salon/speaking.py` (Story 6.15): two lights per pair — the human and their interpreter —
each carrying a colour *and* a shape so colour is never the only carrier (UX-DR7).
`Salon.speaking(...)` broadcasts the whole board to every room, but only when something
actually changed and never to a screen blacked out by driving mode. Detection stays with
LiveKit and Silero; this only carries state between rooms that share nothing.

Driving mode (Story 6.16): `Salon.start_driving`/`stop_driving` suspend everything that only
exists to be looked at — video both ways, captions, and the speaking board. The captions are
the one that costs money, since a translation is billed per turn, so `caption_language` is
emptied for the duration and the `(language, scale)` pair restored on exit — unless a choice
was made during the drive, which `set_captions` records by dropping what was put aside. The
black screen, the wake lock, the whole-surface exit and the low hang-up target are the
client's, in `mobile/src/components/DrivingMode.tsx`.

`Salon.change_mode` (Story 8.5 / FR36) swaps one seat's adapter and nothing else — same
room, same cursor, same `introduced` set, same held queue — then closes the outgoing one. The
cursor is the point: a swap that reset it would replay the whole conversation. Mixed tiers
need no support code at all, since the conductor only talks to the port; a test greps
`conductor.py` for `isinstance` and adapter class names to keep it that way.

### Orchestrator — where an advertisement goes (Story 9.3 / FR39, FR33)

`orchestrator/src/salon/advertising.py` (the `Regie` port, `Diffusion`, `RegieFake`) plus the
placement in `conductor.py`. The exchange is inherited and lives on the API side; this is the
port an interpreter reaches it through and the whole of what the conversation process knows
about advertising.

`Salon.advertising_due(participant_id)` records a **debt** and nothing else — not a coroutine,
because nothing about it can fail or wait. Frequency is the tier's business (FR33); placement
is the Salon's. The draw happens at the placement, not when the moment comes, so the choice is
made against a current record of what this listener has heard.

**The placement rule:** between two messages from two *different* people. A seam alone is not
enough — somebody may carry straight on, and wedging an ad between two of their sentences is
barely better than cutting one in half. The listener's own messages are never one side of the
boundary (they never hear them), a first message has no *between*, and nothing spans a
summary. Past `monologue_ceiling_seconds` the rule is suspended, or one person talking at
length would make the room unreachable by another route.

`_broadcast` spends the slot **whatever came of it** — empty inventory, unreachable exchange,
adapter that could not speak. A debt surviving its own attempt would be retried at every
boundary for the rest of the Salon. `delivered` is called only after the words were actually
spoken, so nothing is billed that nobody heard; both exchange calls swallow exceptions, since
a Salon must not go down because an ad exchange did.

After the ad, `_condense_if_far_behind` runs again: the conversation did not stop while it was
read, and past `condensation_threshold` the backlog is said in substance. No verbatim flag is
needed anywhere — an ad is inserted, never journalled, so no condensation or shortening can
reach the wording Story 9.2 promised word for word.

### API — choosing an advertisement (Story 9.2 / FR39, FR50)

`api/src/ad_selection.py`. The inherited exchange is untouched — auction, billing and proof of
delivery all stay. What the multi-rooms topology changes is *where* an ad goes: one
participant's room, their interpreter, their language. Selection is a **pull**; there is no
shared room to push into.

Two criteria only, cell and language. `ads.topic` stays unwired and a test greps this file to
keep it so — targeting on what a conversation is about is a different consent nobody has been
asked for. Cells compare as exact six-digit strings: a precision mismatch matches nothing
rather than being coerced, so an advertiser who supplied a finer code sees it in their
delivery count instead of having their money spent somewhere they did not choose.

Unheard first, then oldest-heard, so the inventory cycles and never runs dry; the cycle
restarts without accelerating, since frequency belongs to the tier. Generic is a fallback,
never a preference — silence is not an available outcome. `rendered_text` returns
`(text, verbatim)`: a substitution applies to one language only and, when it does, no
cleaning, condensation or shortening may touch it.

The inventory is real (migration 051). `ads_languages` names the languages an ad is meant to
be heard in — a targeting criterion about the humans, not a property of the text — and
`ads_substitutions` holds wording required word for word in one language. Rows rather than
lists, matching `ads_regions`: one ad addresses several regions and several languages with no
row per combination. **Empty on a dimension means unrestricted there; empty on both is what
makes an ad generic**, derived rather than stored, so nothing can claim to be generic while
carrying targeting. `ads.indicative_seconds` is indicative and never contractual — what counts
in the lag is the duration actually rendered.

`inventory(db)` reads the tables into frozen values (no ORM row ever reaches selection, so
nothing lazy-loads mid-Salon); `heard_in_salon(db, salon_id)` reads `ad_broadcasts` for the
**last delivery** of each ad, delivered ones only — the same distinction that stops an
advertiser being charged for a sentence nobody heard.

Migration 051 also drops the third geography: `advertisers.target_countries`, `target_regions`
and the lat/long/radius circle. They were storable and never applicable — `salon_events` holds
a grid cell, not a political boundary. Two ways remain, `ads_regions` and `advertisers_regions`,
both resolving to strings.

### API — location consent (Story 9.1 / FR50)

`api/src/consent.py` + `users.location_consent` (migration 050). The storage was already
careful — `salon_events.plus_code` is a six-digit Open Location Code cell (~5.5 km) encoded at
ingestion, no IP fallback. This adds the *question*.

The column is **nullable on purpose**: three states, not two. `NULL` is "never asked", which
is neither a yes nor a no; a `NOT NULL DEFAULT false` would have recorded a refusal nobody
gave. `targeting_allowed` requires an explicit `True`.

Refusing costs only the targeting — `ad_kind_for` returns `GENERIC`, never "no ads". A test
greps `src/` to confirm nothing outside `consent.py` consults it, so a refusal cannot quietly
degrade anything else. `should_ask` stops the question being re-put after any answer.

Withdrawal bites at *recording*, not reading: `location_cell_for` returns `""` afterwards, so
nothing further is written down. It also truncates to `CELL_DIGITS` even with consent, so a
caller handing over a finer code cannot store a point.

### API — the browser top-up rebate (Story 8.13 / FR70)

`api/src/rebate.py`. A store takes 5–30 % of every purchase through it; a browser payment
avoids that entirely, and handing part of the saving back costs nothing Vocaliz was going to
keep. 5 % is the default because it is covered in **every** combination — a test walks the
whole platform × region × revenue table to hold that, since a rebate that only worked on
average would punish success.

`RebatePolicy` is a mapping so a commission change is a configuration change (FR54); the app
stores stay at zero however the web is configured. A rebate above the commission actually
avoided is **applied but flagged** — an acquisition decision, not something to do by typing a
number. An unknown platform raises rather than defaulting to the web rate.

`EventType.REBATE_GRANTED` keeps it out of `collected` in the paid journal: Stripe took less
than the balance credited, so the difference is a commercial charge. It still counts toward
`outstanding`, because the payer can spend it.

**Not done in 8.13:** the policy is not persisted, so "without a deploy" is only half true —
it needs the Story 7.1 settings treatment.

### API — the paid-balance journal (Story 8.12 / FR68, NFR7)

`api/src/paid_journal.py`, the mirror of the credit journal and also a fold with no table —
same guard. The distinction between them is the point: a gifted credit is a **charge**, a paid
balance is a **debt**, and summing them makes both unreadable.

Four figures, not three: collected, consumed and refunded describe the period; `outstanding`
describes what is still owed at its close. A refund is kept apart from consumption because
money going back out is not money earned.

A paid balance never expires. `dormant_balances` isolates what is owed to people not seen for
`DORMANCY_YEARS`, measuring last activity across the **whole** stream rather than the paid
pool alone — spending gifted credit is activity too, and a narrower clock would write to
somebody who used Vocaliz yesterday. `reminder_due` renews each anniversary while the balance
stays positive, never fires on an empty one, and every reminder is journalled as
`DORMANT_REMINDED` in the one stream. `REMINDER_COPY_TO` copies the operator.

### API — the gifted-credit journal (Story 8.11 / FR67, NFR7)

`api/src/credit_journal.py`. A **fold over the ledger**, with no table of its own — a test
strips the module docstring and then fails on `__tablename__` or `db.add` appearing anywhere
in the code. This is the first place a second table would have been natural, which is why the
guard exists.

Four amounts per credit, and `issued = consumed + expired + abandoned` on every closed entry.
Three closing modes: an account deleted mid-credit is neither consumption nor expiry, and
without `abandoned` as its own state every period total is silently wrong from the first
deletion. Only **consumed** is an expense — it alone bought provider time.

Spending is attributed **oldest credit first**, so somebody holding two has each entry right
rather than only the total. `_gifted` sorts grants ahead of draws at equal timestamps: without
that tie-break a same-instant debit could be folded before its own grant and silently dropped.

### API — manual reactivation credit (Story 8.10 / FR67)

`api/src/reactivation.py`, driven by `python -m src.cli.grant_credit`. An explicit exception
*through* the burned-identifier registry, never a weakening of it: a test asserts the registry
row survives untouched and the welcome credit is still refused afterwards.

`MIN_DAYS_BETWEEN_GIFTS` (90) is what keeps it from being a back door. Every grant carries
`Actor.OPERATOR`, the operator's id and the reason into the ledger — a grant with no reason is
refused, since issuing money with no stated purpose is the entry an audit stops at.
`grant_to_cohort` writes one entry **per beneficiary** and one refusal does not stop the rest.

No screen, no route, no admin accounts table: a test greps `src/routers/` to keep it that way.
Access to production *is* the access control, so there is no administrator authentication to
build and none to get wrong. `confirmation_text` prints the total and head count before
anything is written.

### API — low balance and closing (Story 8.9 / FR55)

`api/src/ending.py`. A host is warned at `HOST_ALERT_COVERAGE_SECONDS` (300) rather than a
guest's 180 — courtesy, not rank: other people's conversation depends on their balance, so
they need longer to decide. `host_alert_text` names the consequence explicitly, because a
decision taken without knowing the Salon closes for everybody is not a decision.

`guest_notice_text` gives the fact and not the cause. A test asserts the words "host",
"balance", "credit", "money" and "budget" are absent — somebody's finances never become
audible to the people they invited.

One alert, then one final reminder under `FINAL_REMINDER_SECONDS` (60), then silence;
`rearm` fires once the balance recovers so the next fall is warned afresh. `ClosingSequence`
is the single bounded exemption to "no consumption without coverage": never billable, asks
the FR26 question like any other ending, and `accepts_speech is False` throughout — the
exemption covers the interpreter's voice, never a resumption, or a free closing would be a
free Salon.

### API — the coverage tick (Story 8.8 / FR56)

`api/src/coverage.py`. `check_coverage` does both halves of one tick, in this order:
**debit what elapsed, then judge the next block**. Verifying first would promise a block the
debit about to happen makes impossible — the one way this can be wrong while looking right.

`block_cost_cents` rounds **up**, the opposite direction to `billing.cost_cents`. A test
asserts the relation that makes it the right direction: the check never demands less than the
billing will take. The debit is on *actually elapsed* seconds, never the nominal cadence,
since jitter at five seconds is not negligible.

Judged per **payer** on the aggregate rate, so a host covering three is evaluated once. Under
`ALERT_COVERAGE_SECONDS` (180) it alerts and asks for exactly one top-up — `already_alerted`
and `top_up_pending` stop a periodic mechanism asking twelve times a minute. Past
`SILENT_WORKER_SECONDS` (60) it charges nothing and ends nothing: silence is a different
problem from an empty balance, and conflating them blames a network failure on a budget.

`validate_top_up_cents` refuses out-of-range amounts **explicitly** rather than clamping —
somebody quietly given 10.00 when they asked for 3.00 finds out from their statement.

**Not done in 8.8:** nothing schedules this tick. The existing 30-second heartbeat is
untouched, and the polite spoken switch-to-Base notice belongs to the interpreter's voice
path.

### API — prepaid metering (Story 8.7 / FR63)

`api/src/metering.py`. Consumption accumulates in whole **cent-seconds** (rate/hour ×
seconds) and becomes cents exactly once, at the boundary, by integer division — no float ever
touches the ledger, because a balance built out of unrepresentable fractions drifts in a
direction nobody chose. `Meter.take_cents()` hands over the whole cents and *keeps the
remainder*, so nothing is lost, only deferred.

`billable_seconds` floors to whole `SAMPLE_SECONDS` (5) blocks: a partial block was never
measured, and billing an unmeasured duration is what gets contested. Under five seconds bills
nothing — an accepted consequence, not an oversight. Rounding is downward in the customer's
favour, deliberately *not* the same as FR63's verification rounding, which goes up.

`effective_rate_cents_per_hour` sums every tier a payer carries plus any telephone
supplement, recomputed instantly when the room changes — free, because the balance stays in
cents and only the rate moves. `remaining_seconds` is a *view* of the cents, never a stored
unit, and returns `None` at a zero rate rather than dividing by it.

**Not done in 8.7:** the recharge flow itself — voice consent, Stripe off-session
`PaymentIntent`, the link fallback across channels, refusal and the 5-minute expiry. Only
`top_up_cents` and the weekly/monthly granularity exist. That half needs Stripe and the
interpreter's voice path.

### API — billing by mode (Story 8.6 / FR22, FR42)

`api/src/billing.py`. `cost_cents(tier, seconds)` prorates to the second and rounds **down**
— a bill should never exceed the thing it is for. `charge_for` takes it from the balance via
`credit.debit` (gifted first) and is **capped at what is there**: the uncovered part is
reported as `shortfall_cents` and `ends_salon`, never owed. That cap is the whole prepaid
design — a system able to invoice past the balance would collect more and would also let
somebody walk away owing money they never agreed to spend.

`charge_for(..., heads=N)` is how the host covering the room is billed: Mode B per head, out
of the host's balance, with every guest's own balance untouched. `host_pays_quote` states the
**maximum** hourly cost in money and `requires_confirmation` until `confirmed()` — "the host
pays" without a number is an option somebody agrees to without knowing what they agreed to.

**Not done in 8.6:** nothing calls `charge_for` yet. The old post-paid path
(`stripe_service`, `users.billed_seconds`, `billing_events`) still runs; this is the new
calculation sitting beside it, not a cutover.

### API — per-participant options (Story 8.4 / FR35, FR42)

`api/src/participation.py` + `salon_participant_options` (migration 049). `join_options`
settles one person's tier, video and top-up as they join. Keyed on (salon, person), not on
the person: somebody may want Mode C for a client call and Base for a chat. Rejoining
replaces rather than duplicating — two rows would leave two answers to "what did they
choose?" and nothing saying which is current.

`salons.host_pays_all` is the host's one offer; what it *produces* still lands per
participant. A guest the host pays for goes to `HOST_PAYS_TIER` (Mode B, so somebody whose
participation is a gift is not also advertised to), is not asked to choose, and is never
asked for money. The override is **only upward** — `_at_least` — because one able to lower an
existing choice would be a host quietly downgrading a guest.

Unlike `ledger_events` and `burned_identifiers`, this table carries FK cascades on purpose:
those are evidence and outlive the account, these are live preferences and do not.

### API — the tier catalogue (Story 8.3 / FR69)

`api/src/tiers.py`. `TierOffer.of(tier)` describes a tier as it appears on the creation
screen: rate, natural voice, advertising, premium voice. The invariant is that each tier adds
exactly **one** thing to the one below — `differences_from` is walked over every neighbouring
pair by a test, because a price gap covering two changes at once is one nobody can evaluate.

`offer_for(db, subject_id)` prices every tier and, when gifted credit remains, times it:
`covers_minutes` on the **remaining** balance, rounded down, and `None` rather than 0 when
there is nothing left — "your credit covers 0 minutes" advertises a disappointment. The
catalogue is identical for everyone; only the credit is personal.

`salons.host_tier` (migration 048) holds the host's own choice. Named for the host on
purpose: a Salon does not have a mode, each participant has one, and a column called `mode`
would assert the opposite by its name. Null means the floor applies — distinct from actively
choosing Base.

### API — the welcome credit (Story 8.2 / FR67)

`api/src/credit.py` + `api/src/models/burned_identifier.py`. 5 USD once per *identifier*, not
per account: a gift given per account is given as often as somebody makes accounts. Every
address and number supplied at signup is checked against `burned_identifiers`, and on a grant
all of them are burned — including ones never used to authenticate. A refusal burns nothing
new. The registry has no FK to users and no expiry column, both deliberately: it must survive
account deletion and outlive the credit's own 30-day lapse.

Balances are folds over the 8.1 stream, never stored totals — `gifted` and `paid` kept apart
so a refund is answerable, gifted spent first so the money actually paid stays intact longest,
and a debit spanning both written as two movements. Expiry is grant + 2 592 000 s to the
second. The warning fires inside the last 7 days, once, never when the balance is already
empty, and states what the money buys per tier rather than a bare date. Labels are canonical
English, translated at rendering like every other participant-facing string.

**Not done in 8.2:** `users.trial_seconds_used` still exists and still drives the old
time-based trial across 10 source files. The new model is complete beside it; the cutover is
its own change.

### API — the accounting event stream (Story 8.1 / NFR7)

`api/src/models/ledger_event.py` + `api/src/ledger.py`. One append-only stream, `ledger_events`,
is the single source of truth for every financial and operational fact — grants, recharges,
debits, refunds, expiries, abandonments. The grant audit (FR66), gifted credits (FR67), paid
balance (FR68) and metrics (NFR4) are **folds** over it, never written alongside it: two
records of one fact drift, and then nothing can say which is right.

Nothing is ever modified or deleted. A correction is a compensating event carrying
`corrects_id`, so both facts survive. Refused twice: by SQLAlchemy `before_update`/
`before_delete` listeners (which the tests exercise) and by a Postgres trigger in migration
046 (which they cannot — there is no Postgres in the suite).

`subject_id` deliberately has **no foreign key**. The inherited `billing_events.host_user_id`
cascaded on the user, so deleting an account destroyed the record of what had been charged to
it. Retention here is independent of accounts. `billing_events` and `ad_broadcasts` are left
in place — cutting their writers over is its own change.

`src/salon/meta_speech.py` (Story 7.6 / FR62) fixes the order the interpreter's own
utterances come out in when several are ready together: BUSY, BALANCE, NOTICE, ADVERT, ties
broken by an arrival counter rather than a clock or object identity, so two runs of one
scenario produce the same audio. `Seat.held` is now this queue and `Salon.announce` takes an
optional `urgency` (defaulting to NOTICE, so no existing caller changes). `drain()` returns
*everything* waiting — it sequences, it does not arbitrate. Introductions, history and the
condensation announcement stay outside the ordering.

`src/load/` (Story 7.5 / FR58, NFR4) is the load harness. `SimulatedSpeaker` generates its
own turns at a chosen cadence, length and language, deterministically and with no provider
call — `InterpreteFake` is reactive and could not do this. `scenario.run` plays a whole
scenario against a *real* Salon in scenario time (an hour finishes in milliseconds), with
`render_speed` giving interpreters a rendering budget so somebody can actually fall behind.
`SalonMetrics` keeps peak lag, p50/p95 latency, the condensed share, blocks counted *and*
timed, and the meta-speech ratio per tier. `Report.of` judges the four ceiling-raise criteria
and fails closed on each: an unmeasured criterion is not a met one.

`src/cohorts.py` (Story 7.5) holds the conversion rate and the delay-to-first-payment
distribution. A cohort inside its 30-day window is marked partial and `compare` raises rather
than warning; the delay is median/p25/p75/p90 and never a mean; non-payers count against the
rate and are excluded from the delay; the delay runs to the first *success* with failures
counted separately.

The monologue ceiling (Story 7.4 / FR56) is `Salon._may_interrupt` plus
`Seat.monologue_seconds`: Story 6.5's rule that nothing third-party is said inside somebody's
intervention is withdrawn past `monologue_ceiling_seconds`, because held with no limit it is
how one person makes everybody else unreachable. Counted per run in seconds of content and
reset at every seam. It starts at 300 like the saturation threshold, with no ordering rule
between them — neither disables the other, so a rule would only refuse working setups.

Saturation (Story 7.3 / FR55) is `Salon._review_saturation` plus `Seat.blocked`: past
`saturation_threshold_seconds` a room speaks `vocaliz_is_busy` to its own participant and
stops accepting their words until the lag drops under `unblock_threshold_seconds`. Ingestion
only — a blocked participant keeps hearing everybody, and is told the moment they speak
rather than dropped in silence. The lag weighed is unheard content (`_unheard_seconds`), so a
long speaker cannot block themselves by talking. It is a state of one room, never of the
Salon, and a mixed Salon is expected. Reviewed after every ingest (head moved) and after
every delivery (cursor moved).

Condensation (Story 7.2 / FR53) lives in `Salon._condense_if_far_behind`: past
`condensation_threshold_seconds` the backlog is said in substance, the cursor jumps to the
end of it and the lag collapses. It is not a mode — every delivery re-weighs the threshold,
so full rendering resumes on its own. `condensed_while_listening` announces it first, naming
how many *people* (not messages) are being summarised, and the listener's own entries are
excluded so nobody is handed the gist of themselves. One interpreter condensing changes
nothing for any other cursor or for the journal.

`src/settings/` (Story 7.1) holds the Salon's *operational* parameters, which is a different
thing from `src/config.py` and deliberately so: a credential should cost a deploy to change,
a threshold should not. They live in a key/value table (`salon_settings`), are read at
startup, and `LiveSettings.get()` re-reads every 30 s so a change reaches a running fleet
without a restart. `condensation_threshold_seconds` and `unblock_threshold_seconds` must both
sit strictly below `saturation_threshold_seconds` — both orderings, if broken, fail silently
rather than loudly, so the configuration is refused with the consequence spelled out.
`create_app(settings_store=...)` injects an `InMemorySettingsStore` for tests; left out, the
instance opens the configured database, which makes an unreachable one a startup failure.

Credentials (`LIVEKIT_*`, `DATABASE_URL`) have no defaults: a missing one fails at startup
with the name in the message. In AWS they come from Secrets Manager via
`ORCHESTRATOR_SECRET_ARN`, the same shape the API uses with `APP_SECRET_ARN`.

The ECS task definition is hand-written JSON in `orchestrator/ecs/task-definition.json` —
no IaC tool for this component. Only `${AWS_ACCOUNT_ID}`, `${ECR_REPOSITORY_URI}` and
`${IMAGE_TAG}` are substituted at deploy time.

## Mobile App (React Native / Expo)

```bash
# Setup (one-time)
cd mobile
npm install

# Start Expo development server (requires Development Build on device, NOT Expo Go)
npm start

# Build Development Client for iOS
npx eas build --platform ios --profile development

# Build Development Client for Android
npx eas build --platform android --profile development

# Run tests (Node's own runner over the pure modules — no bundler, no build step)
npm test
```

Expo has changed: read `https://docs.expo.dev/versions/v57.0.0/` before writing any code
against an Expo module. `mobile/AGENTS.md` says so and it is not decorative.

Automatic driving mode (Story 6.17, FR76) is entirely on the device — the speed is read,
used, and dropped, and nothing about it reaches the orchestrator. `src/lib/drivingAuto.ts`
is a pure state machine over speed samples with no imports at all, which is what makes the
privacy claim checkable: `npm test` fails the build if an import, a `fetch` or a store
appears in it. `src/hooks/useAutoDriving.ts` is the only part that touches `expo-location`,
requests the permission at the moment the automatism is switched on, and watches at
`Accuracy.Balanced` — the lowest that can still tell 5 from 10 km/h.

Two thresholds, never one: on above 10 km/h, off only after 120 s below 5 km/h, so the mode
does not flicker at every junction. Leaving by hand while still moving suspends the
automatism for the rest of the Salon — without it a train passenger is shut inside a safety
feature that was never about them. The automatism only ever undoes its own decisions.

## Key Learnings
- Update this section when you learn new build optimizations
- Document any gotchas or special setup requirements
- Keep track of the fastest test/build cycle

## Feature Development Quality Standards

**CRITICAL**: All new features MUST meet the following mandatory requirements before being considered complete.

### Testing Requirements

- **Minimum Coverage**: 85% code coverage ratio required for all new code
- **Test Pass Rate**: 100% - all tests must pass, no exceptions
- **Test Types Required**:
  - Unit tests for all business logic and services
  - Integration tests for API endpoints or main functionality
  - End-to-end tests for critical user workflows
- **Coverage Validation**: Run coverage reports before marking features complete:
  ```bash
  # Examples by language/framework
  npm run test:coverage
  pytest --cov=src tests/ --cov-report=term-missing
  cargo tarpaulin --out Html
  ```
- **Test Quality**: Tests must validate behavior, not just achieve coverage metrics
- **Test Documentation**: Complex test scenarios must include comments explaining the test strategy

### Git Workflow Requirements

Before moving to the next feature, ALL changes must be:

1. **Committed with Clear Messages**:
   ```bash
   git add .
   git commit -m "feat(module): descriptive message following conventional commits"
   ```
   - Use conventional commit format: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, etc.
   - Include scope when applicable: `feat(api):`, `fix(ui):`, `test(auth):`
   - Write descriptive messages that explain WHAT changed and WHY

2. **Pushed to Remote Repository**:
   ```bash
   git push origin <branch-name>
   ```
   - Never leave completed features uncommitted
   - Push regularly to maintain backup and enable collaboration
   - Ensure CI/CD pipelines pass before considering feature complete

3. **Branch Hygiene**:
   - Work on feature branches, never directly on `main`
   - Branch naming convention: `feature/<feature-name>`, `fix/<issue-name>`, `docs/<doc-update>`
   - Create pull requests for all significant changes

4. **Ralph Integration**:
   - Update .ralph/@fix_plan.md with new tasks before starting work
   - Mark items complete in .ralph/@fix_plan.md upon completion
   - Update .ralph/PROMPT.md if development patterns change
   - Test features work within Ralph's autonomous loop

### Documentation Requirements

**ALL implementation documentation MUST remain synchronized with the codebase**:

1. **Code Documentation**:
   - Language-appropriate documentation (JSDoc, docstrings, etc.)
   - Update inline comments when implementation changes
   - Remove outdated comments immediately

2. **Implementation Documentation**:
   - Update relevant sections in this @AGENT.md file
   - Keep build and test commands current
   - Update configuration examples when defaults change
   - Document breaking changes prominently

3. **README Updates**:
   - Keep feature lists current
   - Update setup instructions when dependencies change
   - Maintain accurate command examples
   - Update version compatibility information

4. **@AGENT.md Maintenance**:
   - Add new build patterns to relevant sections
   - Update "Key Learnings" with new insights
   - Keep command examples accurate and tested
   - Document new testing patterns or quality gates

### Feature Completion Checklist

Before marking ANY feature as complete, verify:

- [ ] All tests pass with appropriate framework command
- [ ] Code coverage meets 85% minimum threshold
- [ ] Coverage report reviewed for meaningful test quality
- [ ] Code formatted according to project standards
- [ ] Type checking passes (if applicable)
- [ ] All changes committed with conventional commit messages
- [ ] All commits pushed to remote repository
- [ ] .ralph/@fix_plan.md task marked as complete
- [ ] Implementation documentation updated
- [ ] Inline code comments updated or added
- [ ] .ralph/@AGENT.md updated (if new patterns introduced)
- [ ] Breaking changes documented
- [ ] Features tested within Ralph loop (if applicable)
- [ ] CI/CD pipeline passes

### Rationale

These standards ensure:
- **Quality**: High test coverage and pass rates prevent regressions
- **Traceability**: Git commits and .ralph/@fix_plan.md provide clear history of changes
- **Maintainability**: Current documentation reduces onboarding time and prevents knowledge loss
- **Collaboration**: Pushed changes enable team visibility and code review
- **Reliability**: Consistent quality gates maintain production stability
- **Automation**: Ralph integration ensures continuous development practices

**Enforcement**: AI agents should automatically apply these standards to all feature development tasks without requiring explicit instruction for each task.
