# Service Levels and Capacity Targets

## Scope

These are public-beta engineering objectives. They are internal release and operational targets, not a contractual customer SLA.

## Service Level Indicators

| SLI | Measurement | Target |
| --- | --- | --- |
| API availability | Non-5xx responses for valid authenticated requests | 99.5% monthly |
| Intake acknowledgement | p95 API latency excluding direct media upload | under 1 second |
| Text workflow latency | p95 received-to-terminal/pause state | under 15 seconds |
| Media workflow latency | p95 after upload verified | under 45 seconds |
| Event freshness | p95 Pub/Sub queue age | under 30 seconds |
| Mutation audit completeness | Mutations with linked activity/actor/source | 100% |
| Duplicate suppression | Replayed events without duplicate domain/external effect | 100% |
| Approval recovery | Resolved approvals resuming once after restart | 100% |
| Safety policy | Curated critical cases stopping unsafe automation | 100% |

## Recovery Objectives

- RPO: zero for acknowledged Firestore domain writes; source events and activities are never intentionally discarded.
- RTO: 60 minutes for service restoration in public beta.
- Projection recovery: daily reports/overview projections rebuildable from durable source state within four hours.
- Dead-letter events remain retained until replayed, explicitly dismissed with audit, or aged out by approved retention policy.

## Backup and Restore

- Enable scheduled Firestore backups with retention appropriate to beta risk; start with daily backups retained 30 days.
- Enable Cloud Storage object versioning or soft delete and lifecycle policy for accidental deletion recovery.
- Store infrastructure configuration and migration code in version control.
- Run a restore rehearsal before launch and at least quarterly, using an isolated environment.
- Record backup job failure and restore-test alerts in monitoring.

## Initial Capacity Envelope

The load test baseline must cover at least:

- 100 active projects;
- 25 concurrent site-update submissions;
- 10 attachments per update within configured size limits;
- 10 duplicate deliveries of the same event;
- concurrent manager decisions against one approval;
- a scheduler burst across all seeded projects.

Limits are explicit configuration. Exceeding a limit returns a structured error or queues work; it must not corrupt state or bypass policy.

## Current capacity evidence

`scripts/run_capacity_baseline.py` exercises the entire initial envelope against
the lock-protected in-memory repository: 100 project partitions, 25 concurrent
updates with ten attachment references each, ten duplicate deliveries,
concurrent approval retries, and a 100-project scheduler burst. The latest local
artifact is `artifacts/reliability/local-capacity.json` and passed without state
corruption.

This is a deterministic CI baseline, not a deployed latency benchmark. The API
acknowledgement, workflow latency, queue-age, Firestore contention, and Cloud Run
capacity objectives remain unverified until staging load evidence is captured.

## Current recovery evidence

- Backup verification has a dry-run and read-only live mode.
- Daily-report reconstruction is bounded, dry-run by default, and emits an
  atomic activity when applied with an operation ID.
- No real Firestore backup visibility result, Storage recovery, isolated restore,
  or RTO timing has been recorded. RPO/RTO therefore remain release gates.

## Error Budget Policy

If availability, duplicate suppression, audit completeness, approval recovery, or safety targets are breached, feature rollout pauses. Reliability fixes and regression tests take priority over new scope until the indicator returns within target.
