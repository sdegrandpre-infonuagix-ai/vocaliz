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
