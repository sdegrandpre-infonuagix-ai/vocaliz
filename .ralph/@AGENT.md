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
```

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
