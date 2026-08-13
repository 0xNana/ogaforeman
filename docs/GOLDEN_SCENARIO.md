# Golden Scenario

## Status

Locked. Conversational work must reuse this path and may not replace it.

## Durable path

```text
authenticated text / voice / photo intake
→ verified attachment persistence
→ site-update event and AgentRun
→ production worker and ADK site-report execution
→ authorized project-context retrieval
→ Gemini structured fact extraction
→ entity resolution and mutation policy
→ typed task, issue, material, report, and approval services
→ durable approval pause
→ persisted approval decision and claimed continuation
→ guarded supplier simulation
→ terminal AgentRun and ActivityEvent timeline
```

Firestore is project truth. Cloud Storage holds original media. Model output never writes either
store directly. Each mutation is authorized, idempotent, and atomically emits an activity.

## Regression evidence

The canonical browser journey is:

```bash
cd frontend
npm run test:e2e -- site-intake.spec.ts --project=mobile-chromium
```

The backing-service restart journey is selected by:

```bash
.venv/bin/python -m pytest -q -m backing_services \
  tests/integration/test_worker_site_update_firestore.py
```

No conversational phase is complete if its focused tests pass but this path regresses.
