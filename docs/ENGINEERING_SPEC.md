# Engineering Specification

## Objective

Build a production-ready, event-driven OG Foreman public beta that turns unstructured site updates into durable project state and completed follow-through. The codebase must preserve a strict boundary: Gemini reasons or performs bounded schema-constrained extraction, ADK coordinates agentic workflows, typed tools perform actions, application services own deterministic ingestion, and Firestore holds project truth. Gemini use alone does not require ADK. Hackathon demo fixtures do not relax production controls.

## Technology Stack

| Layer | Choice | Status |
| --- | --- | --- |
| Backend language | Python 3.12 | Accepted |
| HTTP service | FastAPI and Uvicorn | Accepted |
| Agent runtime | Google ADK 2.x | Accepted |
| Model | Gemini model selected by environment/config | Accepted; do not hard-code production model IDs |
| Validation | Pydantic 2 | Accepted |
| Primary database | Firestore in Native mode | Accepted |
| Media storage | Google Cloud Storage | Accepted |
| Event transport | Pub/Sub with Eventarc triggers | Accepted |
| Compute | Cloud Run API and worker services | Accepted |
| Frontend | Next.js, TypeScript, Tailwind CSS, accessible component primitives | Accepted |
| Server-state client | TanStack Query or Next.js server data primitives, chosen per screen | Proposed |
| Authentication | Firebase Authentication / Identity Platform with canonical Firestore users | Accepted; application composition incomplete |
| Backend tests | pytest | Accepted |
| Frontend tests | Vitest, Testing Library, Playwright | Accepted |
| Infrastructure | Terraform or documented `gcloud` scripts | Proposed; choose once in Phase 1 |

Dependency versions must be pinned through lock files before deployed environments are created. Broad lower bounds in the current `pyproject.toml` are not a release lock.

## Commands

### Commands That Work in the Current Prototype

```bash
python3 main.py --demo
uvicorn main:app --reload --port 8000
pytest -q
```

`pytest` requires the development dependencies to be installed first.

### Target Repository Commands

These commands become mandatory as the corresponding tooling is added:

```bash
uv sync --all-extras --locked
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/python main.py --demo

cd frontend
npm ci
npm run dev
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

The root README must never advertise a command that is not implemented in the repository.

## Target Project Structure

The migration should be incremental. Existing modules may move only when a task requires the new boundary.

```text
app/
  api/                 FastAPI routers, dependencies, request/response types
  agents/              ADK workflow runners, execution bridges, and typed runtime identifiers
  config/              Typed environment and runtime configuration
  domain/              Entity models, enums, policies, and domain errors
  infrastructure/      Firestore, Storage, Pub/Sub, auth, and notification adapters
  prompts/             Versioned prompt templates
  repositories/        Persistence interfaces and Firestore implementations
  services/            Application use cases independent of HTTP and ADK
  tools/               Typed deterministic tools exposed to agents/workflows
  workflows/           Durable workflow definitions and state models
frontend/
  app/                  Next.js route tree
  components/           Reusable domain and primitive components
  lib/                  API client, query keys, auth, formatting
  tests/                Frontend unit/integration tests
tests/
  unit/                 Pure domain, policy, and schema tests
  integration/          Repository, API, workflow, and emulator tests
  contract/             Event, tool, and HTTP compatibility tests
e2e/                    Playwright user journeys
evals/                  Versioned model/workflow evaluation datasets
scripts/                Seed, reset, local emulator, and deployment helpers
infra/                  Reproducible Google Cloud infrastructure
docs/                   Product and engineering source of truth
tasks/                  Executable plan and status checklist
```

## Code Style

Use explicit types, UTC-aware timestamps, immutable input contracts, dependency injection, and domain-specific names. HTTP handlers, ADK agents, and infrastructure adapters should be thin.

```python
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class CompleteTaskCommand:
    project_id: str
    task_id: str
    source_event_id: str
    actor_id: str
    completed_at: datetime


def complete_task(command: CompleteTaskCommand, repository: TaskRepository) -> Task:
    task = repository.require(command.project_id, command.task_id)
    return repository.save(task.complete(at=command.completed_at.astimezone(UTC)))
```

Conventions:

- Python modules and functions: `snake_case`; classes: `PascalCase`; constants: `UPPER_SNAKE_CASE`.
- TypeScript variables/functions: `camelCase`; components/types: `PascalCase`.
- IDs are opaque strings with stable prefixes such as `prj_`, `tsk_`, `evt_`, and `run_`.
- Domain status values are enums, not unchecked strings.
- Do not use mutable default arguments.
- Use timezone-aware `datetime.now(UTC)`, not `datetime.utcnow()`.
- Tool and API errors use stable machine-readable codes.
- Comments explain non-obvious intent or constraints, not line-by-line behavior.
- Prompt templates are versioned and tested like code.

## Testing Strategy

| Level | Purpose | Dependencies |
| --- | --- | --- |
| Unit | Domain invariants, policies, matching, calculations, schemas | No network, model, or cloud |
| Tool contract | Typed tool input/output, authorization, idempotency, activity emission | In-memory/fake repositories |
| Integration | Firestore/Storage/Pub/Sub adapters, API routes, workflow persistence | Local emulators or isolated test project |
| Workflow | State transitions, retries, approval pause/resume, failure paths | Fake model and deterministic adapters |
| Eval | Extraction and reasoning quality across normal/adversarial cases | Versioned model configuration |
| E2E | Mobile intake, manager approval, activity, daily brief | Full local/deployed stack |

Requirements:

- Every mutation tool has success, authorization, validation, idempotency, and activity tests.
- Every workflow has happy path, ambiguous input, duplicate event, retry, and terminal failure tests where applicable.
- External model calls are not used in ordinary unit tests.
- E2E tests may replace model, object-storage, and event-transport dependencies at
  their external boundaries. Those substitutes must not create domain state or
  decide workflow transitions: browser submissions must enter the production event
  worker and use the production repositories, coordinator, mutation, approval,
  outbox, and continuation code. Request interception or a parallel state machine
  is not evidence for workflow status.
- Persistence acceptance tests must use fresh clients against the Firestore and
  Storage emulators; reusing an in-memory store or object dictionary is not restart
  evidence. CI runs non-backing tests separately, then starts both emulators and
  executes every `backing_services` test with no conditional skip.
- Release candidates pass the locked evaluation thresholds and the global definition of done below.

## Engineering Boundaries

### Multimodal Site-Update Contract

- The API persists and links verified attachment metadata before publishing a
  site-update event. The worker must reload both the `SiteUpdate` and private
  object bytes; frontend memory, blob URLs, and client-supplied transcripts are
  not processing dependencies.
- Audio transcription is derived state. Its text and source attachment IDs are
  saved on the existing `SiteUpdate` in the same transaction as a redacted
  `site_update.transcribed` activity before structured fact extraction starts.
- Retries retain the immutable submitted event payload, reuse the same
  deterministic update/run IDs, and skip audio IDs with a persisted transcript.
  A media/model failure transitions the update and run to recoverable failed
  state for the event claim retry.
- Images are sent to the configured Gemini adapter as inline bytes with their
  verified MIME types and bounded authorized project context. Model output still
  passes through fact validation, entity resolution, policy, and typed mutation
  services.
- A photo without corroborating text or transcript cannot by itself create a
  high-confidence completion mutation. Visual uncertainty must produce an
  observation/clarification and a durable waiting state.
- The aggregate inline-media limit is configurable below Gemini's request cap;
  Storage reads enforce size and SHA-256 again at consumption time.

### Blocker-Impact Contract

- An actionable blocker fact may identify a task only through authorized project
  context and deterministic entity resolution. The matched task is transitioned by
  the typed task service; model output never supplies a database path or arbitrary ID.
- The resolved task ID enters the canonical dependency-impact calculation. A separate
  delay-risk issue contains only graph-supported downstream task IDs; task titles and
  construction phrases do not decide impact. Completed and cancelled descendants stop
  traversal and are not presented as future schedule risks.
- Blocker and delay-risk issues project into the source-linked daily report. The
  concise risk summary and pending review action are persisted on the originating
  `AgentRun` before completion or approval/clarification pause and are exposed by the
  authorized run API.
- A task-linked blocker also creates one typed `TaskSource.SITE_UPDATE` follow-up.
  The mutation verifies the persisted blocker, source site update, and blocked task
  in the authorized project transaction, inherits only the blocked task's canonical
  assignee ID, stores all three source references, and atomically emits
  `task.follow_up_created`. Its idempotency scope is part of the originating event/run;
  the model cannot provide an assignee or arbitrary entity ID.

### Approval Continuation Contract

- The canonical processing state is `SiteUpdate.PROCESSING` with its `AgentRun`
  `RUNNING`; a pending purchase atomically transitions them to their respective
  `WAITING_FOR_APPROVAL` states. The different enum labels must not be collapsed
  into an untyped browser status.
- Resolving an approval persists the decision and linked request transition first.
  It must not execute an external action inside the decision transaction or move
  the original run out of its waiting state before the continuation event is claimed.
- A continuation reloads the persisted approval, linked request, and run selected by
  the request's source event. It validates the decision status and canonical resolver;
  event payload alone cannot authorize a resume or rejection.
- Resume, rejection terminalization, and successful terminal completion each commit
  a system-attributed, idempotent `ActivityEvent` atomically with the corresponding
  `AgentRun` change. The resolver remains the actor on the separate approval-decision
  activity; the worker must not impersonate that user. Approval does not fabricate
  supplier acceptance, confirmation, or delay.
- Rejection persists decision notes, leaves no external action, cancels or
  rejects the request, and terminalizes the same logical run. Approval replay and
  event redelivery cannot execute the external action or terminal transition twice.

### External Delivery Notification Contract

- A real delay enters through the authenticated operator endpoint as one
  normalized `DELIVERY_DELAYED` event; production code contains no delay generator.
- The dedicated ADK graph loads the authorized project, canonical material
  request, material, and affected tasks before calculating dependency impact.
- Google Chat is the single V1 external destination. Its incoming webhook URL
  is a Secret Manager value, is never logged, and is mandatory in deployed environments.
- `NotificationService` owns the durable delivery lifecycle. It accepts the
  `NotificationProvider` contract: `LoggingNotificationProvider` is restricted
  to development/tests, while `GoogleChatNotificationProvider` is the sole
  `RealExternalNotificationProvider`. Staging and production require the
  explicit `NOTIFICATION_PROVIDER=google_chat` setting.
- A typed allowlisted payload is persisted to the outbox before network I/O.
  It contains project/event identity, the canonical material request, affected
  work, risk severity, OG's completed action summary, and an optional safe link.
  It contains no authorization object, webhook credential, prompt, or model reasoning.
  Outbox queue, claim, retry, failure, and completion mutations emit atomic activities.
- Provider delivery uses deterministic Google Chat `requestId` and `messageId`
  values derived from the source event and destination. An expired local claim
  retries the same provider identity instead of creating a second logical message.
- Transient HTTP/network failures use bounded exponential backoff. Permanent
  failures are dead-lettered, remain observable, and prevent `AgentRun` success
  without rolling back or corrupting the already-valid project risk and follow-up.

### Workflow Audit Contract

- Existing mutation activities remain stable. Semantic workflow activities add
  causality without replacing or projecting a second state machine: received media,
  authorized context, interpreted fact counts, detected risks, pause/resume, external
  execution, report update, and terminal workflow outcome all reference the original
  source event and `AgentRun`.
- Workflow activity names come from a typed registry and their idempotency scopes are
  deterministic. Redelivery creates no duplicate event; a transactionally completed
  mutation keeps its original atomic activity even when a separate semantic event is
  also recorded.
- Activity metadata is an allowlisted diagnostic envelope containing bounded
  canonical IDs, counts, statuses, quantities, and observable reason codes. It never
  contains prompts, transcripts, evidence prose, raw media, object/signed URLs,
  credentials, secrets, or hidden model reasoning.
- `AgentRun.updated_at` advances on every persisted lifecycle/checkpoint transition.
  The authorized run API exposes stable run/project/trigger/workflow identity,
  status, step, attempt, trace ID, start/update/completion timestamps, and bounded
  error fields while retaining the existing `id` field for compatibility.

### Always Do

- read `PRODUCT.md`, `SECURITY_SAFETY.md`, and the active task before coding;
- validate inputs at service boundaries;
- route project writes through repositories and typed tools;
- create an `ActivityEvent` in the same logical transaction as each mutation;
- make event consumers and workflow steps idempotent;
- preserve tenant/project authorization context;
- add tests before or with behavior changes;
- update contracts and docs when behavior changes.

### Ask First

- add a new core workflow or product area;
- change the database model in a backward-incompatible way;
- add a paid service or major dependency not in the accepted stack;
- change authentication strategy;
- lower a safety/approval threshold;
- expose a new public integration endpoint;
- replace Google ADK workflow primitives with custom orchestration.

### Never Do

- store project truth only in prompts, model context, process memory, or browser state;
- let model-generated text execute arbitrary database operations;
- log secrets, raw auth tokens, chain-of-thought, or unnecessary personal data;
- auto-approve purchases, external commitments, task cancellation, or safety-critical actions;
- claim structural, engineering, or safety certification;
- commit credentials or edit generated/vendor directories by hand;
- remove a failing test merely to make CI green;
- add billing, credits, subscriptions, or feature gating to V1.

## Global Definition of Done

A task is done only when:

- its acceptance criteria are met;
- relevant automated tests pass;
- lint, format, and type checks pass for touched languages;
- errors and empty/loading/retry states are handled;
- authorization, validation, idempotency, and audit behavior were considered;
- docs, API contracts, evals, and seed data are updated when affected;
- no secrets or high-risk debug output were introduced;
- The implementation status record and `tasks/todo-v1.md` reflect the result.

A release is done only when:

- the four core workflows pass end-to-end;
- the seeded demo can be reset and repeated;
- duplicate delivery causes no duplicate mutations;
- approval pause/resume survives a process restart;
- core mobile and desktop flows pass accessibility and browser checks;
- deploy, smoke test, rollback, and operational runbooks are verified.

The release also clears every production-readiness control. A passing happy-path demo is insufficient if restart, concurrency, duplicate delivery, authorization, approval recovery, or API-backed UI tests fail.

## Open Engineering Decisions

- Terraform versus checked-in `gcloud` scripts for infrastructure provisioning.
- Which login providers, if any, follow the initial Email/Password public-beta flow.
- Whether the first deployed V1 uses one Cloud Run image with two entrypoints or separate API/worker images.
- Exact Gemini model IDs and fallback policy after measuring eval quality, latency, and cost.
