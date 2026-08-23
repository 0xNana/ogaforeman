# HTTP API Contract

> **Implementation status:** uploads, site-update intake, approvals, project
> snapshots, project-import creation/recovery/review, task/material setup, internal event publication, health, and dead-letter inspection have
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
The response also includes nullable `adk_session_id`, `adk_invocation_id`, and `adk_workflow_id` correlation fields for authorized diagnostics.
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
activities, latest report, historical `dailyLogs`, verified photos, and PDF
documents. Attachment projections retain source and linked-record IDs while file
content remains behind authorized signed-read URLs. A newly created project
therefore returns empty resource lists plus its persisted `project.created` activity rather than a
hard-coded empty projection.

Task entries in the snapshot expose `needsAttention` and `sourceRefs`. A current
site-update follow-up is therefore visible in Tasks and Needs You from persisted API
state, while its source site update, blocker issue, and blocked task remain
reconstructable without frontend session memory.

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

`POST /projects` accepts `name`, `location`, `timezone`, optional `description`,
optional ISO `start_date` and `target_end_date`, and an optional lowercase project
`status`. Existing clients that omit status retain the `active` default; the New
Project wizard explicitly starts projects in `planning`. The caller owns the
required `Idempotency-Key` and must reuse it after a timeout. An exact replay
returns the original project, while reusing the key with different project fields
returns `409 DUPLICATE_IDEMPOTENCY_KEY`. Project creation atomically writes the
project, administrator membership, and `project.created` activity.

### Project Initialization Imports

```text
POST /projects/{project_id}/imports
GET  /projects/{project_id}/imports?limit=10&status=...&nonterminal=false
GET  /projects/{project_id}/imports/{import_id}
POST /projects/{project_id}/imports/{import_id}/retry
POST /projects/{project_id}/imports/{import_id}/confirm
POST /projects/{project_id}/imports/{import_id}/cancel
```

`POST /imports` accepts `source_name`, `source_type`, and exactly one bounded
payload: `source_text` for `text`/`markdown`, or `source_data_base64` for `file`
and `spreadsheet`. Supported files are `.docx`, `.xlsx`, `.xls`, `.csv`, and
text-based `.pdf`; Google Docs must first be exported to `.docx` or `.pdf`.
Bounded server adapters validate the extension/type pair and format, then enforce
archive expansion, page, row, cell, raw-file, and 800 KB extracted-text limits
before model invocation. BIM, Primavera, MS Project, invalid, encrypted, and
image-only PDF sources are rejected. The caller must retain and replay its
`Idempotency-Key` after a timeout. Exact replay resumes the same source and import
identity. Extraction is rate-limited per canonical user and project (with IP as
an additional abuse signal) before source persistence or model invocation.

`GET /imports` is an authorized, newest-first recovery feed bounded to 1–50
records. `status` filters one lifecycle state. `nonterminal=true` excludes
`imported` and `cancelled` before applying the limit, so `limit=1` reliably
recovers the latest active import even when newer terminal imports exist. The
summary returns IDs, status, optimistic version, safe failure code/message,
retryability, timestamps, and draft entity counts; it never returns source text,
prompts, or raw model output. Reads require active project membership; creation,
retry, confirmation, and cancellation require project management permission.

`POST /imports/{import_id}/retry` accepts `expected_version` and a stable
`Idempotency-Key`. It reuses the persisted `ProjectSource` for extraction failures
and retryable model-reference conflicts; it never requires the client to upload
the source again. Exact replay returns the current result without another model
call. A stale version or changed retry claim returns `409`, and canonical writes
remain blocked until the replacement draft passes deterministic validation and
is explicitly confirmed.

The authorized detail response additionally exposes bounded diagnostics:
`telemetry_trace_id`, prompt/model registry keys, diagnostic stage/attempt, and
validation/commit outcomes. These fields correlate safe logs and traces without
exposing the source, generated body, prompt body, credentials, or chain-of-thought.

Confirmation and cancellation require `expected_version` plus a stable
`Idempotency-Key`. On the first import into an empty project, confirmation also
atomically applies the reviewed project name, location, description, dates, and
status while preserving the project's timezone and identity. Later additive
imports do not replace project metadata. Canonical records are created only by
successful confirmation; cancellation does not mutate canonical project truth.

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
POST /projects/{project_id}/materials
GET /projects/{project_id}/material-requests
GET /projects/{project_id}/approvals
GET /projects/{project_id}/reports/{report_date}
POST /projects/{project_id}/daily-logs/{report_id}/edit
GET /projects/{project_id}/activity
GET /projects/{project_id}/agent-runs/{run_id}
POST /conversations/messages
POST /projects/{project_id}/conversations/messages
```

The authenticated user-scoped conversation endpoint accepts bounded product-help and project-setup
questions. Product help does not resolve a project or call Gemini; setup resolves the user's sole
project, reports that no project exists, or asks the user to open one when the choice is ambiguous.
The project-scoped conversation endpoint accepts one bounded message with optional authorized attachment
IDs and returns one stable discriminated shape. `kind` includes `casual`, `help`, `project`,
`advice`, `clarification`, `proposed_change`, and `workflow`; all responses include user-facing
`text`, `cited_record_ids`, `mutation_performed`, and `assistant_name: "OG"`. Internal `intent`
metadata is available to diagnostics but must not be rendered as the author or a user-facing badge.
Advice may add `recommendation`; proposals may add `proposed_action`; Golden workflow handoffs may
add `workflow_run_id`. Project actions and site updates require an `Idempotency-Key`. A proposed
change is not a completed mutation.

The additive agent-run response exposes `id` and its explicit alias `run_id`,
`project_id`, `trigger_event_id`, `workflow`, `status`, `step`, `attempt`,
`trace_id`, `started_at`, `updated_at`, `completed_at`, `result_summary`,
`pending_actions`, `error_code`, and `error_summary`. For site updates the summary
and actions are the concise, user-safe OG response persisted on the exact run
before it completes or pauses; clients do not reconstruct them from browser state.
The response also includes nullable `adk_session_id`, `adk_invocation_id`, and
`adk_workflow_id` correlation fields for authorized diagnostics.

Example response:

```json
{
  "id": "run_01JEXAMPLE",
  "run_id": "run_01JEXAMPLE",
  "project_id": "prj_ridge",
  "trigger_event_id": "evt_01JEXAMPLE",
  "workflow": "daily_site_update",
  "status": "waiting_for_approval",
  "step": "approval_required",
  "attempt": 1,
  "trace_id": "evt_01JEXAMPLE",
  "adk_session_id": "agents-ogaforeman/run_01JEXAMPLE-attempt-1",
  "adk_invocation_id": "evt_01JEXAMPLE",
  "adk_workflow_id": "daily_site_update_workflow",
  "started_at": "2026-08-09T10:00:00Z",
  "updated_at": "2026-08-09T10:00:04Z",
  "completed_at": null,
  "result_summary": "Processed the site update and prepared one material request.",
  "pending_actions": ["Manager approval required for the cement request."],
  "error_code": null,
  "error_summary": null
}
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
  "notes": "Approve the material request for external coordination.",
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
POST /projects/{project_id}/delivery-delays
```

`POST /projects/{project_id}/delivery-delays` requires authenticated project
`OPERATE` permission plus an `Idempotency-Key`. It accepts a canonical material
request ID, revised delivery date, stated reason, and optional aware occurrence
time; it persists one normalized `DELIVERY_DELAYED` event before publication.
Delivery-delay input is authenticated, normalized, persisted, and published.
The public API does not expose a generic `ProjectEvent` injection route and
request data cannot select an arbitrary workflow name.

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
