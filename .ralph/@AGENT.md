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
