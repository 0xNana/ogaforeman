# Requirements Traceability

| Requirement/control | Domain | Event | Workflow | API/UI | Tests/evals | Task IDs |
| --- | --- | --- | --- | --- | --- | --- |
| Durable state / restart safety | Project, AgentRun, ProcessedEvent | All | All | All project reads | Persistence + restart | F-02, F-03 |
| Duplicate suppression | ProcessedEvent, fingerprints | `idempotency_key` | All | `Idempotency-Key` | Replay/concurrency | F-04, R-01 |
| Site update intake | SiteUpdate, Attachment | `SITE_UPDATE_RECEIVED` | Daily Site Update | upload/site-update routes, mobile composer | Intake E2E | F-06, S-01 |
| Structured interpretation | ExtractedFactSet | fact contract | Daily Site Update | run/activity views | evals normal/mixed/ambiguous | A-02, A-03, W-01 |
| Progress accuracy | Task invariants | `TASK_COMPLETED` | Progress branch | task view | negation/precision | A-04, W-01 |
| Materials follow-through | Material ledger/request | material events | Material Shortage | materials/approvals | approval/resume/rejection | M-01..M-04 |
| Blocker impact | Issue, dependencies | blocker/delay events | Blocker and Delay | issues/tasks/activity | safety/delivery evals | B-01..B-03 |
| Daily brief | DailyReport | `DAILY_BRIEF_REQUESTED` | Daily Brief | report/notification views | scheduled brief | D-01, D-02 |
| Human approval | Approval state machine | granted/rejected | Materials/impact | approval decision route/UI | restart and conflict | M-03, M-04 |
| Auditability | ActivityEvent | all | all | activity/run routes | mutation contract | R-02 |
| Authentication/tenant isolation | User, ProjectMember, ProjectAccessContext | canonical actor | all | Firebase Bearer token and project auth dependencies; see `AUTH.md` | token, role, disabled-user, cross-project, and browser-session tests | F-06, S-01, R-01 |
| Media validation | Attachment | upload metadata | Site Update | signed upload route | upload security | F-07, R-04 |
| API-backed UI | projections | status events | all | versioned routes | Playwright | S-01..S-04 |
| Observability | AgentRun/Activity | correlation | all | run detail | trace smoke | R-03 |
| SLO/recovery | Source entities/events | all | all | health/status | load, backup, restore | R-04, L-01 |
| Demo reset | seed project | deterministic fixture | all | admin script | repeated reset | L-01 |
