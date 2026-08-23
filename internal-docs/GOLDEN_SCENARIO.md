# Golden Scenario

## Status

Locked and P0. New conversational feature work and demo recording are blocked
until the billed Vertex evaluation passes all eight operational checks. A green
project-import evaluation does not satisfy this gate.

## Live release checks

The live evaluator uses one canonical update and the production fact-extraction
prompt. Gemini returns evidence-backed facts and names only. Deterministic
services own canonical IDs, entity resolution, calculations, mutations,
approval, and the delivery event.

1. `blockwork_completion`: canonical First-floor blockwork reaches completed.
2. `electrical_blocker`: one blocker and follow-up resolve to Electrical rough-in.
3. `cement_inventory`: canonical Cement Bags stock becomes 10 bags.
4. `cement_requirement`: First-floor plastering resolves as next focus against a
   persisted 100-bag requirement.
5. `shortage_90_bags`: deterministic arithmetic produces exactly 90 bags.
6. `material_request`: one canonical request is awaiting approval.
7. `approval`: one linked purchase approval is pending and no supplier action
   occurs before the human decision.
8. `delivery_delay`: approval triggers the guarded supplier simulator, and the
   later typed event marks the same request delayed with an audited risk.

Canonical entity resolution is an aggregate metric across the same checks and
must be 100%. The case pass rate must be 8/8.

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

Run the deterministic gate:

```bash
.venv/bin/python scripts/run_golden_evals.py --adapter fixture
```

Run the required billed Vertex gate:

```bash
.venv/bin/python scripts/run_golden_evals.py \
  --adapter gemini \
  --backend vertex \
  --output artifacts/evals/golden-live-gemini.json
```

Do not record until the live artifact belongs to the submitted commit and has
`passed: true`, `case_pass_rate: 1.0`, and
`canonical_entity_resolution_accuracy: 1.0`. The report must also identify the
Vertex project/location and show `source_tree_dirty: false`.

The 2026-08-23 billed Vertex attempt achieved 8/8 and 100% canonical resolution
with `gemini-3.5-flash`, but is deliberately not release evidence because it ran
from a dirty source tree.
