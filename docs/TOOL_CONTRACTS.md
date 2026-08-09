# Deterministic Tool Contracts

## Non-Negotiable Rules

Tools are the only path from agent/workflow output to durable mutations. Each tool validates auth, domain policy, entity IDs, versions, units, and idempotency independently of the model. Successful mutations and their `ActivityEvent` commit atomically.

## Common Context

```python
class ToolContext(BaseModel):
    project_id: str
    actor_type: Literal["user", "agent", "system"]
    actor_id: str | None
    source_event_id: str | None
    agent_run_id: str | None
    idempotency_key: str | None
```

Every result is typed. Errors use stable codes, a safe message, retryability, and structured details.

## Read Tools

```text
get_project(project_id) -> Project
get_project_context(project_id, workflow, entity_hints) -> ContextBundle
list_tasks(project_id, filters, cursor) -> Page[Task]
get_task_dependencies(project_id, task_ids) -> DependencyGraph
get_material(project_id, material_id_or_alias) -> MaterialView
list_open_issues(project_id, filters, cursor) -> Page[Issue]
list_pending_approvals(project_id) -> Page[Approval]
get_daily_report(project_id, report_date) -> DailyReport
get_agent_run(project_id, run_id) -> AgentRunView
```

Read tools never accept an arbitrary collection path and never return records from another project.

## Mutation Tools

```text
record_site_update(input, context) -> SiteUpdate + ProjectEvent
update_task_progress(input, context) -> TaskChange
complete_task(input, context) -> TaskChange
create_issue(input, context) -> IssueChange
update_material_quantity(input, context) -> MaterialLedgerChange
create_material_request(input, context) -> MaterialRequestChange
create_approval(input, context) -> ApprovalChange
resolve_approval(input, context) -> ApprovalChange + ContinuationEvent
create_daily_report(input, context) -> DailyReportChange
notify_user(input, context) -> NotificationChange
record_activity(input, context) -> ActivityEvent
```

## Policy Examples

- `complete_task` requires explicit positive evidence, a known task ID, valid version, and a non-blocked task.
- `update_material_quantity` uses canonical material ID/unit and a ledger event; it cannot make stock negative.
- `create_material_request` deduplicates open equivalent requests and creates an approval for purchases in V1.
- `resolve_approval` requires manager/admin role and a transactionally pending approval; a second decision returns a conflict/no-op.
- `notify_user` deduplicates by project, source event, notification type, and recipient.

## Error Codes

```text
AUTH_PROJECT_FORBIDDEN
ROLE_REQUIRED
ENTITY_NOT_FOUND
VALIDATION_FAILED
INVALID_STATE_TRANSITION
DUPLICATE_IDEMPOTENCY_KEY
CONFLICT_VERSION_MISMATCH
APPROVAL_REQUIRED
SAFETY_ESCALATION_REQUIRED
EXTERNAL_ACTION_PENDING
EXTERNAL_ACTION_FAILED
RETRYABLE_DEPENDENCY_FAILURE
```

## External Side Effects

Supplier submission and external notifications use persisted outbox/action claims. A retry checks the claim before doing anything external. The simulated supplier is deterministic and records status transitions; it is not a hidden purchase integration.

## Contract Test Matrix

Every tool has tests for valid input, invalid input, unauthorized project/role, duplicate idempotency key, concurrent version conflict, activity contents, retry classification, and relevant approval/safety gates.
