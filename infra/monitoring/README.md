# Monitoring controls

These checked-in alert-policy templates cover the Phase 8 minimum operational
signals: API 5xx ratio, API p95 latency, worker queue age, dead-letter backlog,
backup-verification failures, slow project-import extraction, repeated import
extraction failure, and project-import commit failure.

`infra/deploy.sh` renders `${API_SERVICE}`, `${WORKER_SUBSCRIPTION}`, and
`${DEAD_LETTER_SUBSCRIPTION}` into temporary files before applying them. The
backup policy depends on the `oga_backup_failure_count` logs-based metric created
by the same deployment script.

## Staging smoke

After staging credentials and a deployed API URL are available:

```bash
.venv/bin/python scripts/smoke_observability.py \
  --base-url "$OGA_STAGING_API_URL" \
  --output artifacts/operations/staging-observability.json
```

Then use the emitted trace ID to find the matching `http_request_finished` log
in Cloud Logging and the corresponding span in Cloud Trace. Trigger each alert
only in staging, record the incident URL and recovery timestamp, and restore the
threshold immediately afterward.

Project-import policies use log-derived counters from the bounded
`project_import_stage_finished` event. Labels never contain project, import,
source, prompt body, or model response content. The incident procedure is in the
Project import incidents section of `docs/OPERATIONS.md`.

The deployed staging API and exact Cloud Logging correlation are recorded in
`artifacts/operations/staging-observability.json` and
`artifacts/operations/staging-log-correlation.json`; eight policies are provisioned.
Cloud Trace span visibility and an alert-delivery incident are still open and
must not be inferred from the log-correlation pass.

## Dead-letter handling

Do not acknowledge or replay a dead-letter message until the persisted
`ProcessedEvent` record and its failure code have been inspected.

1. Pull without acknowledging:

   ```bash
   gcloud pubsub subscriptions pull "$DEAD_LETTER_SUBSCRIPTION" \
     --project "$GOOGLE_CLOUD_PROJECT" \
     --limit 10 \
     --format json
   ```

2. Confirm the project-scoped event metadata through
   `GET /api/v1/projects/{project_id}/dead-letters` as an authorized manager or
   administrator.
3. Correct the root cause and verify the event fingerprint/idempotency key.
4. Republish the original immutable envelope to the site-events topic.
5. Acknowledge the dead-letter message only after the replay reaches a terminal
   persisted state.

Never edit an event payload to force a replay; create a new event with a new
idempotency key when the business fact itself changed.
