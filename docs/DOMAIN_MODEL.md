# Domain Model

## Modeling Rules

- `project_id` is present on every project-owned entity and is used for authorization and partitioning.
- IDs are opaque, immutable, and generated once. Human-readable numbers are display fields only.
- Timestamps are UTC-aware ISO 8601 values at API boundaries and Firestore timestamps at rest.
- Status values are explicit enums with documented transitions.
- User-authored input is never overwritten by extracted or corrected data.
- Derived projections such as overall progress and daily briefs can be rebuilt from source entities and activity events.

## Entities

### User

```text
id: string
identity_subject: string  # verified external identity subject; unique mapping to id
display_name: string
email: string
avatar_url: string | null
status: active | disabled
created_at: datetime
updated_at: datetime
```

### Project

```text
id: string
name: string
location: string
description: string | null
timezone: IANA timezone
start_date: date | null
target_end_date: date | null
status: planning | active | paused | completed | archived
created_by: user_id
created_at: datetime
updated_at: datetime
```

### ProjectMember

```text
project_id: string
user_id: string
role: admin | manager | foreman | viewer
status: invited | active | removed
created_at: datetime
updated_at: datetime
```

`User.id` is the canonical application identity used by domain records and audit actors.
`identity_subject` is the verified Firebase/Identity Platform subject used only to resolve that
canonical user; display name and email are never identity keys. A project request is authorized
only when the resolved canonical user has an active membership in the requested project.

### Task

```text
id: string
project_id: string
title: string
description: string | null
status: proposed | planned | in_progress | blocked | completed | cancelled
priority: low | medium | high | critical
assigned_to: user_id | null
planned_start: datetime | null
planned_end: datetime | null
actual_start: datetime | null
actual_completion: datetime | null
dependency_ids: string[]
completion_percent: number [0, 100]
source: manual | site_update | workflow | import
version: integer
created_at: datetime
updated_at: datetime
```

### SiteUpdate

```text
id: string
project_id: string
submitted_by: user_id
input_type: text | voice | photo | mixed | file
raw_text: string | null
transcript: string | null
attachment_ids: string[]
client_event_id: string
processing_status: received | processing | waiting_for_clarification | completed | failed
submitted_at: datetime
processed_at: datetime | null
created_at: datetime
updated_at: datetime
```

### Attachment

```text
id: string
project_id: string
site_update_id: string | null
object_path: string
content_type: audio/* | image/* | application/pdf | other allowlisted type
byte_size: integer
sha256: string
upload_status: initiated | uploaded | verified | rejected | deleted
metadata: map<string, scalar>
created_at: datetime
```

### Issue

```text
id: string
project_id: string
type: blocker | delay_risk | safety | quality | observation
severity: info | low | medium | high | critical
description: string
evidence_refs: string[]
task_ids: string[]
status: open | acknowledged | mitigated | resolved | dismissed
detected_by: site_update | overdue_check | delivery_event | user
owner_id: user_id | null
due_at: datetime | null
resolved_at: datetime | null
created_at: datetime
updated_at: datetime
```

### Material

```text
id: string
project_id: string
name: string
normalized_name: string
unit: string
available_quantity: number
reserved_quantity: number
minimum_required_quantity: number
upcoming_requirement_quantity: number | null
estimated_unit_cost: number | null
default_supplier: string | null
updated_at: datetime
```

### MaterialRequest

```text
id: string
project_id: string
material_id: string
quantity: number
unit: string
needed_by: datetime | null
reason: string
source_event_id: string
supplier: string | null
estimated_total_cost: number | null
status: proposed | awaiting_approval | approved | rejected | submitted | confirmed | delayed | delivered | cancelled
approval_id: string | null
created_at: datetime
updated_at: datetime
```

### Approval

```text
id: string
project_id: string
action_type: purchase | schedule_change | external_commitment | task_cancel | high_impact_change
proposed_action: map<string, scalar | list>
reason: string
evidence_refs: string[]
status: pending | approved | rejected | expired | cancelled
requested_by: system | user_id
requested_at: datetime
resolved_at: datetime | null
resolved_by: user_id | null
resolution_notes: string | null
version: integer
```

### DailyReport

```text
id: string
project_id: string
report_date: date
summary: string
completed_work: list<ReportFact>
active_blockers: list<ReportFact>
material_risks: list<ReportFact>
next_focus: list<ReportFact>
source_update_ids: string[]
status: draft | published
created_at: datetime
updated_at: datetime
```

### AgentRun

```text
id: string
project_id: string
trigger_event_id: string
workflow: daily_site_update | material_shortage | blocker_delay | daily_brief
status: queued | running | waiting_for_approval | waiting_for_clarification | completed | failed | dead_lettered
attempt: integer
step: string
started_at: datetime
completed_at: datetime | null
trace_id: string
error_code: string | null
error_summary: string | null
```

### ActivityEvent

```text
id: string
project_id: string
actor_type: user | agent | system
actor_id: string | null
action: string
entity_type: string
entity_id: string
summary: string
metadata: map<string, scalar | list | object>
source_event_id: string | null
agent_run_id: string | null
created_at: datetime
```

### ProcessedEvent

```text
id: string  # deterministic idempotency key
project_id: string
event_id: string
event_type: string
status: claimed | completed | failed | dead_lettered
result_ref: string | null
first_seen_at: datetime
completed_at: datetime | null
attempts: integer
last_error_code: string | null
```

This technical entity is required for at-least-once event delivery and is not shown as a product feature.

## Relationships

```text
User --< ProjectMember >-- Project
Project --< Task --< dependency >-- Task
Project --< SiteUpdate --< Attachment
Project --< Issue >-- Task (many-to-many references)
Project --< Material --< MaterialRequest >-- Approval
Project --< DailyReport
Project --< AgentRun --< ActivityEvent
Project --< ProjectEvent --< ProcessedEvent
```

## Invariants

1. A project member can read or mutate only projects for which their membership is active.
2. A task cannot be completed with a completion percentage below 100.
3. A completed task cannot move back to in-progress without an explicit user correction recorded as an activity.
4. A blocked task cannot be silently marked completed by an automated workflow.
5. Dependency IDs must reference tasks in the same project; cycles are rejected at write time.
6. Available material quantity cannot become negative. Reservation and delivery operations use separate ledger entries or transactions.
7. A material request quantity must be positive and use the material's canonical unit.
8. An approval may transition out of `pending` exactly once.
9. A safety/structural issue with `high` or `critical` severity stops the current autonomous mutation branch.
10. Every domain mutation has exactly one source event or explicit human actor and at least one activity event.
11. A daily report is unique per `(project_id, report_date)`.
12. An event ID is unique within a project and remains stable across retries.
13. Completion/resolution timestamps are present only for terminal states and cannot precede the
    entity's submitted, created, requested, started, or first-seen timestamp.
14. A human correction may reopen a completed task to `in_progress`; it does not bypass the rest
    of the task transition policy or revive cancelled state.

## Firestore Collection Layout

```text
projects/{project_id}
projects/{project_id}/members/{user_id}
projects/{project_id}/tasks/{task_id}
projects/{project_id}/issues/{issue_id}
projects/{project_id}/materials/{material_id}
projects/{project_id}/material_requests/{request_id}
projects/{project_id}/approvals/{approval_id}
projects/{project_id}/site_updates/{site_update_id}
projects/{project_id}/attachments/{attachment_id}
projects/{project_id}/daily_reports/{report_date}
projects/{project_id}/agent_runs/{run_id}
projects/{project_id}/activity/{activity_id}
projects/{project_id}/events/{event_id}
projects/{project_id}/processed_events/{idempotency_key}
users/{user_id}
```

Use explicit subcollections for project-owned data so security rules and repository queries have a clear project boundary. Add composite indexes only for measured query patterns.

## Seed Project

The deterministic demo project must include:

- `Ridge Project` (or the final chosen display name) with a configured timezone;
- completed foundation work;
- first-floor blockwork planned/in progress;
- electrical rough-in dependent on blockwork;
- plastering planned for the next day and dependent on materials;
- cement stock below the plastering requirement after the demo update;
- one manager member and one foreman member;
- at least two photo placeholders and a reset-safe event ledger.

Seed and reset behavior is specified in `DEMO.md`.
