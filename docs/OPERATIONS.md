# Operations Runbook

## Signals

The API and worker emit structured JSON logs with bounded correlation fields:
request, correlation, trace, project, event, run, workflow, step, retry, status,
duration, and safe error code. Raw site text, media, credentials, auth headers,
signed URLs, and chain-of-thought are excluded.

Endpoints:

```text
GET /healthz   process liveness
GET /readyz    configuration, Firestore, and Storage readiness
GET /metrics   bounded Prometheus-format local metrics
```

The checked-in monitoring policies alert on API 5xx ratio, API p95 latency,
worker queue age, dead-letter backlog, and backup-verification failures.

## Staging observability smoke

```bash
.venv/bin/python scripts/smoke_observability.py \
  --base-url "$OGA_STAGING_API_URL" \
  --output artifacts/operations/staging-observability.json
```

Find the emitted trace ID in Cloud Logging and Cloud Trace. A local pass proves
only HTTP/correlation contracts; staging trace correlation and alert delivery
require real cloud evidence.

## Dead-letter handling

1. Pull without acknowledging:

   ```bash
   gcloud pubsub subscriptions pull "$DEAD_LETTER_SUBSCRIPTION" \
     --project "$GOOGLE_CLOUD_PROJECT" \
     --limit 10 \
     --format json
   ```

2. As an authorized manager/admin, inspect persisted metadata through
   `GET /api/v1/projects/{project_id}/dead-letters`.
3. Confirm the event fingerprint, idempotency key, attempt count, error code,
   and affected project. Never copy raw secrets into an incident.
4. Fix and verify the root cause. Republish the original immutable envelope only
   when replay is safe; create a new event if the business fact changed.
5. Acknowledge the dead-letter message only after the replay reaches a persisted
   terminal state.

## Backup and restore

Read-only verification:

```bash
.venv/bin/python scripts/verify_backups.py \
  --project-id "$GOOGLE_CLOUD_PROJECT" \
  --bucket "$MEDIA_BUCKET" \
  --live \
  --output artifacts/operations/backup-check.json
```

The verifier requires a recent READY Firestore backup and Storage versioning or
soft delete. It does not claim restore success.

Restore rehearsal:

1. Select a backup predating a seeded, reversible staging mutation.
2. Restore to a separate Firestore database/project; never overwrite production.
3. Verify project isolation, tasks, materials, approvals, activities, events, and
   object recovery.
4. Rebuild a bounded daily report in dry-run first:

   ```bash
   .venv/bin/python scripts/rebuild_projections.py \
     --project-id prj_ridge \
     --report-date 2026-08-08 \
     --timezone Africa/Accra \
     --max-activities 500
   ```

5. Apply only with an incident/rehearsal operation ID:

   ```bash
   .venv/bin/python scripts/rebuild_projections.py \
     --project-id prj_ridge \
     --report-date 2026-08-08 \
     --timezone Africa/Accra \
     --max-activities 500 \
     --apply \
     --operation-id restore-rehearsal-2026-08-08
   ```

6. Record backup name, restored database, object generation, timings, activity
   ID, and teardown approval. Compare against the RTO/RPO in `SLOS.md`.

## Common incidents

### Stuck workflow

- Find the event/run/approval and last persisted checkpoint.
- Confirm whether a human decision or clarification is legitimately pending.
- Retry through the event/workflow boundary; never edit state without activity.
- If the continuation route is PR-04, keep the incident open until the worker
  actually resumes the persisted run.

### Duplicate event alarm

- Inspect the `ProcessedEvent` fingerprint and activity/outbox counts.
- Disable an external adapter immediately if a side effect duplicated.
- Reconcile the external system, then add a regression test before resuming.

### Cross-project access report

- Revoke affected credentials/session where appropriate.
- Preserve request, user, project, repository, and trace evidence.
- Add a two-project authorization regression before restoring access.

### Unsafe site update

- Confirm the qualified human has been notified.
- Ensure the affected automation branch remains stopped.
- Do not let a product status substitute for engineering/safety certification.

## Rollback

Use `infra/rollback.sh` with explicit verified API and worker revisions. Preserve
events and activities. After traffic shift, run readiness, event delivery,
duplicate suppression, and approval-resume checks. A successful command without
those smokes is not a completed rollback rehearsal.
