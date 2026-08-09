# HTTP API Contract

> **Implementation status:** uploads, site-update intake, approvals, project
> resources, internal event publication, health, and dead-letter inspection have
> typed implementations. Site-update intake reaches the claimed worker and ADK
> workflow path; endpoints still marked as proposed below remain target contracts.

## API Rules

- Base path: `/api/v1`.
- JSON responses use a stable envelope for errors and explicit resource schemas for success.
- Every request accepts or receives `X-Request-ID`; server logs correlate it with `correlation_id`, `event_id`, and `trace_id`.
- Long-running work returns `202 Accepted` with a resource ID and status URL.
- All project-owned routes require authentication and active membership.
- Mutation routes require an `Idempotency-Key` header; the key is scoped to the authenticated project/user and endpoint.
- The API never exposes model chain-of-thought or raw secrets.

## Error Envelope

```json
{
  "error": {
    "code": "AUTH_PROJECT_FORBIDDEN",
    "message": "You do not have access to this project.",
    "request_id": "req_01JEXAMPLE",
    "details": {}
  }
}
```

Stable HTTP mapping:

```text
400 VALIDATION_FAILED / EVENT_TYPE_UNSUPPORTED
401 AUTH_REQUIRED
403 AUTH_PROJECT_FORBIDDEN / ROLE_REQUIRED
404 ENTITY_NOT_FOUND
409 CONFLICT_VERSION_MISMATCH / DUPLICATE_IDEMPOTENCY_KEY
413 UPLOAD_TOO_LARGE
415 MEDIA_TYPE_UNSUPPORTED
422 SAFETY_ESCALATION_REQUIRED / APPROVAL_REQUIRED
429 RATE_LIMITED
500 INTERNAL_ERROR
503 DEPENDENCY_UNAVAILABLE
```

## Authentication and Headers

The normative identity, browser-session, role, and workload contract is in
[AUTH.md](AUTH.md).

Required for protected routes:

```text
Authorization: Bearer <identity-token>
X-Request-ID: optional opaque request ID
Idempotency-Key: required on POST/PATCH/decision mutations
```

The backend verifies the Firebase token and resolves its `sub` claim to one
active canonical `User.id`. It then loads the active project membership, checks
the required permission, and passes an immutable `ProjectAccessContext` through
repository and tool access. Email and display name are never identity keys.

`main.py` installs the provider when auth settings are present. Local settings
without an auth audience intentionally fail closed. The project snapshot reads
the authorized project's persisted tasks, materials, requests, approvals,
activities, and latest report. A newly created project therefore returns empty
resource lists plus its persisted `project.created` activity rather than a
hard-coded empty projection.

## Endpoint Catalog

### Projects

```text
GET    /projects
POST   /projects
GET    /projects/{project_id}
GET    /projects/{project_id}/snapshot
PATCH  /projects/{project_id}
GET    /projects/{project_id}/members
POST   /projects/{project_id}/members
```

### Project State

```text
GET /projects/{project_id}/overview
GET /projects/{project_id}/tasks
POST /projects/{project_id}/tasks
PATCH /projects/{project_id}/tasks/{task_id}
GET /projects/{project_id}/tasks/{task_id}/dependencies
GET /projects/{project_id}/issues
PATCH /projects/{project_id}/issues/{issue_id}
GET /projects/{project_id}/materials
GET /projects/{project_id}/material-requests
GET /projects/{project_id}/approvals
GET /projects/{project_id}/reports/{report_date}
GET /projects/{project_id}/activity
GET /projects/{project_id}/agent-runs/{run_id}
```

### Site Update Intake

```text
POST /projects/{project_id}/uploads/sign
POST /projects/{project_id}/uploads/{attachment_id}/verify
GET  /projects/{project_id}/uploads/{attachment_id}/read-url
POST /projects/{project_id}/site-updates
GET  /projects/{project_id}/site-updates/{site_update_id}
GET  /projects/{project_id}/site-updates/{site_update_id}/status
```

`/uploads/sign` validates the intended content type, exact byte size, SHA-256 checksum, canonical
attachment ID, project permission, and server-derived object path. It returns a short-lived V4
`PUT` URL whose signed headers bind the content type, content length, and create-only generation
precondition. The client must send every returned `required_headers` entry exactly.

After the direct upload, `/verify` reads the private object, re-checks its exact path, stored size,
declared type, byte signature, and server-computed SHA-256, then atomically persists verified or
rejected `Attachment` metadata with an `ActivityEvent`. Repeating a successful verification is a
no-op. `/read-url` is project-authorized and returns a short-lived private `GET` URL only for a
verified attachment.

Example signing request:

```json
{
  "attachment_id": "att_photo001",
  "content_type": "image/jpeg",
  "byte_size": 204800,
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

Example `201` response:

```json
{
  "attachment_id": "att_photo001",
  "project_id": "prj_ridge",
  "object_path": "projects/prj_ridge/attachments/att_photo001",
  "upload_url": "https://storage.googleapis.com/private-bucket/...?X-Goog-Signature=...",
  "expires_at": "2026-08-07T08:56:00Z",
  "required_headers": {
    "Content-Type": "image/jpeg",
    "Content-Length": "204800",
    "x-goog-if-generation-match": "0"
  },
  "max_bytes": 52428800
}
```

The site-update request references only attachment IDs whose status is `verified`.

Example site-update request:

```json
{
  "input_type": "mixed",
  "raw_text": "Blockwork is done. The electrician did not come.",
  "attachment_ids": ["att_photo_1"],
  "occurred_at": "2026-08-07T08:41:00Z"
}
```

Example `202` response:

```json
{
  "site_update_id": "su_01JEXAMPLE",
  "event_id": "evt_01JEXAMPLE",
  "agent_run_id": "run_01JEXAMPLE",
  "status": "queued",
  "status_url": "/api/v1/projects/prj_ridge/agent-runs/run_01JEXAMPLE"
}
```

### Approval Decisions

```text
POST /projects/{project_id}/approvals/{approval_id}/decision
```

Request:

```json
{
  "decision": "approved",
  "notes": "Proceed with the simulated supplier request.",
  "expected_version": 0
}
```

The optimistic `expected_version` prevents a decision from overwriting a newer
manager action. A stale decision returns `409 CONFLICT_VERSION_MISMATCH`. The
response returns the current approval projection; the persisted outbox event
resumes the linked workflow. The caller cannot choose a workflow, tool,
supplier action, or project ID in the decision payload.

### Events and Integrations

```text
POST /projects/{project_id}/events
POST /internal/events  # service-to-service, authenticated workload identity only
```

External events are authenticated per adapter, normalized, persisted, and published. They do not execute arbitrary workflow names from request data.

### Worker delivery endpoints

The private worker service exposes two infrastructure-only HTTP routes outside
`/api/v1`:

```text
POST /pubsub/push             authenticated Pub/Sub push envelope
POST /scheduler/daily-brief  authenticated Cloud Scheduler request
```

Cloud Run IAM must reject unauthenticated callers. `/pubsub/push` decodes and
validates one immutable `ProjectEvent`, claims it, routes it through the worker,
and acknowledges successful/duplicate delivery. `/scheduler/daily-brief`
calculates a stable local reporting window and publishes a deterministic
`DAILY_BRIEF_REQUESTED` event. Neither route accepts an arbitrary workflow name.

## Pagination and Filtering

- Use opaque cursor pagination with `limit` capped at 100.
- Every list endpoint requires a project path and supports only documented filters.
- Activity and site update feeds sort by server timestamp and stable ID.

## Caching and Consistency

- Project overview may use short-lived cache headers only for reads.
- Approval, activity, task mutation, and run status reads must be strongly consistent enough for manager decisions.
- The UI refetches after mutations and on visibility regain; it never treats cached metrics as authoritative.

## OpenAPI and Contract Tests

Generate or maintain an OpenAPI document from FastAPI types. Contract tests must verify response schemas, error codes, authorization, idempotency, and that no endpoint returns fields outside its documented projection.
