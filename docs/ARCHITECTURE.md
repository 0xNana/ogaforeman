# Target Architecture

## Status

Accepted for V1 implementation. See ADRs in `docs/decisions/` for rationale.

## Architectural Rule

> Gemini reasons or performs bounded extraction. ADK coordinates agentic workflows. Typed tools perform actions. Application services own deterministic ingestion. Firestore remains the source of truth.

No model response, agent session, browser cache, or process-local object is authoritative project state.

## System Context

```text
Site Foreman -----+
                  |
Project Manager --+--> Next.js Web/PWA --> FastAPI API --> Firestore
                  |                         |    |         Cloud Storage
Admin ------------+                         |    +-------> Pub/Sub
                                            |                 |
External events ----------------------------+                 v
                                                       ADK Worker
                                                            |
                                               Gemini reasoning + tools
                                                            |
                                              Firestore + Activity Log
```

## Runtime Components

### Web Application

- Responsive Next.js application optimized for mobile site input and desktop manager review.
- Establishes a Firebase browser session and attaches current ID tokens only to protected API requests.
- Handles upload initiation, project navigation, activity views, and approval actions after authentication resolves.
- Treats server state as authoritative; optimistic updates are allowed only for reversible UI state.
- Keeps the public deterministic demo isolated from authenticated project data and API fallbacks.

### API Service

- FastAPI service deployed to Cloud Run.
- Verifies Firebase identity, resolves the subject to a canonical Firestore user, and enforces project membership/role authorization according to [AUTH.md](AUTH.md).
- Issues signed Cloud Storage upload instructions.
- Persists inbound site updates and normalized events.
- Serves project state, activities, approvals, reports, and workflow status.
- Publishes asynchronous work and returns `202 Accepted` for long-running processing.

### Workflow Worker

- Cloud Run service subscribed through Pub/Sub/Eventarc.
- Claims events idempotently and starts/resumes the correct ADK workflow.
- Loads only relevant project context.
- Invokes Gemini specialists for structured reasoning.
- Invokes deterministic tools for reads and mutations.
- Persists workflow checkpoints so retries and approval pauses survive restarts.

### Scheduler

- Cloud Scheduler publishes `DAILY_BRIEF_REQUESTED` events per project schedule.
- A scheduler job never generates the report directly; it enters through the same event contract as other triggers.

### Firestore

- Primary system of record for domain entities, workflow state, activities, idempotency claims, and configuration.
- Repository interfaces isolate domain/application code from Firestore details.
- Transactions or conditional writes protect idempotency and coupled mutation/activity writes.

### Cloud Storage

- Stores original audio, photos, and files under project-scoped object paths.
- Firestore stores metadata and references, not binary content.
- Upload validation and object finalization events prevent untrusted files from entering workflows prematurely.

### Pub/Sub and Eventarc

- Deliver normalized project events to the worker.
- At-least-once delivery is assumed; consumers must be idempotent.
- Retry policy ends in a dead-letter topic handled by operations tooling.

### Observability

- Structured Cloud Logging for API requests, event handling, workflow steps, tools, and errors.
- Cloud Trace correlation from inbound request/event through model and tool calls.
- Metrics for queue age, success/failure, approval wait time, duplicate suppression, and model latency.

## Request and Event Flow

### Protected Project Request

```text
1. Firebase resolves the browser session and issues a current ID token.
2. Client sends Authorization: Bearer <identity-token>.
3. API verifies token audience, issuer, expiry, and subject.
4. API resolves the subject to an active canonical User.id.
5. API loads active project membership and checks the route permission.
6. Immutable ProjectAccessContext crosses service/repository/tool boundaries.
7. Repository and tool guards recheck project scope and permission.
```

This is the accepted target flow. The verifier and authorization components
exist, but the current main application and frontend do not yet compose the
complete path.

### Site Update

```text
1. Client requests signed upload details.
2. Client uploads media directly to Cloud Storage.
3. Client POSTs site update metadata and text.
4. API validates membership, media ownership, and idempotency key.
5. API persists SiteUpdate + ProjectEvent and publishes event.
6. API returns 202 with site_update_id and workflow status URL.
7. Worker claims event and starts Daily Site Update workflow.
8. Interpreter returns typed facts with evidence/confidence.
9. Workflow fans out to progress, blocker, and material branches.
10. Tools mutate project state and append ActivityEvents.
11. Workflow updates the daily report and user-facing response.
12. Client observes status through polling initially; streaming is optional after V1.
```

### Approval Pause and Resume

```text
1. Workflow creates Approval and checkpoint with state WAITING_FOR_APPROVAL.
2. Manager sees approval in the command center.
3. Manager POSTs an idempotent decision.
4. API records the decision with resolver identity.
5. API publishes APPROVAL_GRANTED or APPROVAL_REJECTED.
6. Worker loads the checkpoint and resumes exactly once.
7. Downstream tool executes or cancellation is recorded.
```

## Internal Layering

```text
API / Event adapters
        |
Application services and workflows
        |
Domain entities and policies
        |
Repository/tool interfaces
        |
Firestore, Storage, Pub/Sub, auth, notification adapters
```

Rules:

- Domain code imports no FastAPI, Firestore, ADK, or UI package.
- Workflows depend on tool interfaces and structured agent interfaces.
- Tools enforce authorization/policy again; they do not trust model output.
- Infrastructure adapters translate external errors into stable domain/application errors.

## Deployment Topology

V1 uses two Cloud Run services:

| Service | Ingress | Responsibility |
| --- | --- | --- |
| `oga-api` | Public, authenticated where required | HTTP API and health/readiness endpoints |
| `oga-worker` | Internal/Eventarc | Event processing and workflow execution |

They may share one container image initially with different entrypoints, but they must not share in-memory state.

Supporting resources:

- Firestore Native database;
- Cloud Storage media bucket;
- Pub/Sub main and dead-letter topics/subscriptions;
- Eventarc triggers;
- Cloud Scheduler daily brief job;
- Secret Manager configuration;
- service accounts with least-privilege IAM;
- Artifact Registry repository;
- Cloud Logging, Monitoring, and Trace.

## Consistency and Transactions

- Firestore document IDs are generated before mutations so activity references are stable.
- A domain mutation and its `ActivityEvent` are committed in one Firestore transaction or atomic batch.
- Repository transactions use a callback-style `run_transaction` contract so Firestore can start,
  retry, and commit the complete unit of work. Transaction callbacks read before writing and must
  contain no non-idempotent external side effect.
- Event claim documents use create-if-absent semantics.
- Approval resolution uses a version/precondition so two decisions cannot both win.
- Reports are projections and can be rebuilt from durable source entities/activity if necessary.

## Failure Model

| Failure | Required behavior |
| --- | --- |
| Model timeout/transient error | Retry step with bounded exponential backoff |
| Invalid structured model output | One repair attempt, then clarification or failed run |
| Firestore conflict | Retry transaction; do not rerun non-idempotent external action blindly |
| Duplicate event | Return original processing result or no-op with duplicate activity metadata |
| Media unavailable | Keep update pending and retry; surface user-visible failure after terminal state |
| Approval wait | Persist state without consuming a worker instance |
| Notification failure | Record failure and retry independently from core project mutation |
| Poison event | Dead-letter with run/error references and no silent data loss |

## Scaling Boundaries

- Project ID is the primary partition/authorization boundary.
- Event processing should preserve per-project logical ordering where required, but unrelated projects may process concurrently.
- Large media never passes through the API process.
- Context retrieval is bounded by task status, recency, and workflow needs rather than loading an entire project into a prompt.
- External integrations are adapters behind typed tools and are not introduced into the core domain.

## Migration from the Prototype

1. Freeze schemas and repository interfaces before replacing `_PROJECT_DB`.
2. Build an in-memory repository implementation for fast tests.
3. Add Firestore implementations and seed/reset scripts.
4. Move direct dictionaries and workflow functions behind application services.
5. Introduce event claim/activity infrastructure.
6. Replace keyword extraction with a structured interpreter behind a fakeable interface.
7. Introduce durable ADK workflow checkpoints and approval resumption.
8. Replace the static dashboard with the Next.js application against the versioned API.

At no point should the prototype dictionary become a second production source of truth.
