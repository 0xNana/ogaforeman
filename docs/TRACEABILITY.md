# Requirements Traceability

| Requirement/control | Domain | Event | Workflow | API/UI | Tests/evals | Task IDs |
| --- | --- | --- | --- | --- | --- | --- |
| Durable state / restart safety | Project, AgentRun, ProcessedEvent | All | All | All project reads | Persistence + restart | F-02, F-03 |
| Duplicate suppression | ProcessedEvent, fingerprints | `idempotency_key` | All | `Idempotency-Key` | Replay/concurrency | F-04, R-01 |
| Site update intake | SiteUpdate, Attachment | `SITE_UPDATE_RECEIVED` | Daily Site Update | upload/site-update routes, mobile composer | Intake E2E | F-06, S-01 |
| Structured interpretation | ExtractedFactSet | fact contract | Daily Site Update | run/activity views | evals normal/mixed/ambiguous | A-02, A-03, W-01 |
| Progress accuracy | Task invariants | `TASK_COMPLETED` | Progress branch | task view | negation/precision | A-04, W-01 |
| Materials follow-through | Material ledger/request | material events | Material Shortage | materials/approvals | approval/resume/rejection | M-01..M-04 |
| Blocker impact and follow-through | Issue, dependencies, source-linked Task | blocker/delay events | Blocker and Delay | issues/tasks/Needs You/activity | worker/replay/restart/browser | B-01..B-03, P0.4, P0.5 |
| Daily brief | DailyReport | `DAILY_BRIEF_REQUESTED` | Daily Brief | report/notification views | scheduled brief | D-01, D-02 |
| Human approval | Approval state machine | granted/rejected | Materials/impact | approval decision route/UI | restart and conflict | M-03, M-04 |
| Auditability | ActivityEvent | all | all | activity/run routes | mutation contract | R-02 |
| Authentication/tenant isolation | User, ProjectMember, ProjectAccessContext | canonical actor | all | Firebase Bearer token and project auth dependencies; see `AUTH.md` | token, role, disabled-user, cross-project, and browser-session tests | F-06, S-01, R-01 |
| Media validation | Attachment | upload metadata | Site Update | signed upload route | upload security | F-07, R-04 |
| API-backed UI | projections | status events | all | versioned routes | Playwright | S-01..S-04 |
| Observability | AgentRun/Activity | correlation | all | run detail | trace smoke | R-03 |
| SLO/recovery | Source entities/events | all | all | health/status | load, backup, restore | R-04, L-01 |
| Demo reset | seed project | deterministic fixture | all | admin script | repeated reset | L-01 |
| Project initialization source/review | ProjectSource, ProjectImportRecord, draft contracts | exact create/decision claims | Project Initialization Import | import create/list/detail/confirm/cancel and New Project wizard | lifecycle, recovery, cross-project, prompt-injection, rate-limit | PI-01..PI-08, PI-12 |
| Imported operational truth | Task, dependency, Material, MaterialRequirement, ledger, provenance | atomic import activity | Project Initialization Import + four V1 workflows | initialized snapshot | 90/70 shortage, dependency impact, typed material evolution, replay/restart | PI-09, PI-10, PI-13 |
| Import diagnostics | persisted trace and typed registry keys | stage outcome logs | source through commit trace | authorized import detail | bounded metrics/logs, alert policies, smoke | PI-11 |
| Initialization release recovery | all source/import/canonical/activity records | persisted claims | import recovery | authenticated staging and post-rollback reads | live eval artifact, staging smoke, rollback preservation | PI-13, PI-14 |
