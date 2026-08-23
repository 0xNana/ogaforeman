# Project Event Contract

## Purpose

`ProjectEvent` is the stable boundary between input sources and OG Foreman's workflows. Web input, schedules, delivery adapters, and future integrations normalize into this contract instead of adding source-specific coordinator branches.

## Envelope

```json
{
  "schema_version": "1.0",
  "event_id": "evt_01JEXAMPLE",
  "project_id": "prj_ridge",
  "event_type": "SITE_UPDATE_RECEIVED",
  "source": "web",
  "occurred_at": "2026-08-07T08:41:00Z",
  "received_at": "2026-08-07T08:41:02Z",
  "actor": {"type": "user", "id": "usr_foreman"},
  "idempotency_key": "site-update:su_01JEXAMPLE:v1",
  "correlation_id": "req_01JEXAMPLE",
  "payload": {
    "site_update_id": "su_01JEXAMPLE",
    "text": "First-floor blockwork is done. Electrician did not come.",
    "transcript": null,
    "attachment_ids": ["att_photo_1", "att_photo_2"]
  },
  "metadata": {}
}
```

## Required Fields

| Field | Rule |
| --- | --- |
| `schema_version` | Major version changes require a compatibility plan |
| `event_id` | Opaque and unique within a project |
| `project_id` | Must match authenticated/project context |
| `event_type` | Registered type only |
| `source` | `web`, `scheduler`, `supplier`, `integration`, or `system` |
| `occurred_at` / `received_at` | UTC-aware timestamps |
| `actor` | Verified user, workload, system, or integration identity |
| `idempotency_key` | Stable across delivery retries |
| `correlation_id` | Connects request, event, run, and trace |
| `payload` | Type-specific validated object |

## V1 Event Registry

| Event type | Required payload | Route |
| --- | --- | --- |
| `SITE_UPDATE_RECEIVED` | update ID and text/transcript/attachments | Daily Site Update |
| `TASK_COMPLETED` | task ID and evidence refs | Report/projection follow-up |
| `TASK_BLOCKED` | issue description, severity, task refs | Blocker and Delay |
| `MATERIAL_LOW` | material ref/name, quantity, unit | Material Shortage |
| `MATERIAL_REQUESTED` | request ID | Materials continuation |
| `DELIVERY_DELAYED` | request ID, new date, reason | Materials plus Blocker impact |
| `APPROVAL_GRANTED` | approval ID, resolver, notes | Resume checkpoint |
| `APPROVAL_REJECTED` | approval ID, resolver, notes | Cancel checkpoint branch |
| `TASK_OVERDUE` | task ID and expected date | Blocker and Delay |
| `DAILY_BRIEF_REQUESTED` | report date and timezone | Daily Brief |

Unknown types return `EVENT_TYPE_UNSUPPORTED`; they never fall through to another workflow.

`DELIVERY_DELAYED` enters through `POST
/api/v1/projects/{project_id}/delivery-delays`. Firebase authentication,
project `OPERATE` authorization, the `Idempotency-Key` header, canonical request
lookup, schema validation, an atomic intake activity, and a persisted Pub/Sub
outbox precede worker execution. No production component synthesizes this event.

## Extracted Facts

Interpreter output is validated separately from the event envelope:

```json
{
  "facts": [
    {
      "fact_id": "fact_1",
      "kind": "completed_work",
      "subject": "first-floor blockwork",
      "entity_hint": "tsk_blockwork_floor_1",
      "value": {"completion_percent": 100},
      "evidence": ["First-floor blockwork is done."],
      "confidence": 0.98,
      "negated": false,
      "requires_clarification": false
    }
  ],
  "unresolved_questions": [],
  "model_id": "configured-at-runtime",
  "prompt_version": "site-interpreter/1.0"
}
```

Allowed fact kinds:

```text
completed_work
progress_update
blocker
material_observation
material_shortage
delivery_change
schedule_observation
safety_observation
general_observation
```

## Validation and Routing

- Reject missing identifiers, unsupported versions/types, invalid/naive timestamps, negative quantities, and percentages outside `[0, 100]`.
- Do not silently clamp values.
- `almost done`, `nearly complete`, future-tense completion, or negated work cannot produce a completion mutation.
- Low-confidence entity matches create an observation or clarification request.
- Safety facts pass through safety policy before normal branches.
- Event payloads are immutable; corrections create a new event referencing the original.

## Delivery Semantics

- Pub/Sub delivery is at least once.
- Worker creates `processed_events/{idempotency_key}` using create-if-absent before mutation.
- Duplicate completed events return the stored result/no-op without rerunning tools or notifications.
- Claimed events use a bounded lease so abandoned work can be reclaimed.
- Bounded retries end in a dead-letter topic with event/run/error references.
- Correctness reads current entity versions; it does not rely on global message ordering.

### Processed-event claim record

Each `projects/{project_id}/processed_events/{idempotency_key}` record persists:

- the event ID, schema version, type, and deterministic event fingerprint;
- status (`claimed`, `completed`, `failed`, or `dead_lettered`), attempt count, and repository
  version;
- an opaque claim token and UTC lease expiry only while actively claimed;
- a result reference and completion timestamp for successful replay;
- bounded error summary plus dead-letter timestamp and reason after terminal failure.

The fingerprint covers every immutable envelope field using canonical JSON ordering and UTC
timestamp normalization. Reusing an idempotency key for a different event identity or fingerprint
is a conflict. Idempotency keys are bounded to 256 path-safe characters; payloads and metadata are
bounded JSON with finite numbers, collection/depth limits, and deep immutability. Completion and
failure require both the current claim token and an unexpired lease, so a worker that lost
ownership cannot finalize after another worker reclaims the event. Busy/dead-letter replay results
never expose another worker's claim token.

## Versioning

Additive fields are backward-compatible within a major version. Removing a field or changing its meaning requires a new major version, dual compatibility during migration, and contract tests for both versions.
