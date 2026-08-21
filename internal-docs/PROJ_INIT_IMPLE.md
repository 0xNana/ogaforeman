# Project Initialization Production-Completion Plan

## Status

Implemented locally. PI-00 through PI-14 and the bounded office-document adapter
extension are complete; external staging preservation and rollback evidence
remain release gates. This plan closes the gaps found while auditing the current
implementation against [`PROJECT_INIT.md`](PROJECT_INIT.md).

This document does not expand the four-workflow V1 scope. Project initialization
creates the trusted project data those workflows operate on; it is not a fifth
operational workflow.

## Product outcome

Project initialization starts at **New Project**, not at an undiscoverable import
URL. An administrator must be able to complete this production journey:

```text
New Project
    ↓
Project details
    ↓
Choose setup method
    ├── Import an existing plan (recommended V1 path)
    │       ↓
    │   Word / Excel / PDF / CSV / text / Markdown / OG template
    │       ↓
    │   Extract → validate → review
    │       ↓
    │   Confirm & Initialize
    │       ↓
    │   Operational project
    │
    └── Start empty
            ↓
        Manual task/material setup
            ↓
        Partially configured project
```

Creating the project and initializing its plan are distinct durable operations.
The project is created first so every source, import, draft, trace, and mutation is
project-scoped. If extraction fails, the project remains valid and the setup flow
resumes without creating another project.

## Locked V1 scope

V1 must support:

- project details: name, location, timezone, description, start date, target end
  date, and status;
- a visible setup choice inside the New Project journey;
- pasted text, Markdown, the OG structured-text template, `.docx`, `.xlsx`,
  legacy `.xls`, `.csv`, and text-based `.pdf` sources;
- durable source persistence and checksum;
- Gemini schema-constrained extraction through the Google Gen AI / Vertex model
  API; project initialization is an ingestion pipeline, not an agent workflow;
- deterministic normalization, validation, duplicate detection, and commit;
- review of tasks, dates, dependencies, materials, requirements, warnings,
  conflicts, initial task state, and opening inventory;
- explicit confirmation before canonical project records are created;
- project-scoped provenance, activity, observability, recovery, and authorization;
- canonical task-specific material and dependency reasoning after import.

V1 does not add Primavera, MS Project, BIM, scanned-document OCR, quantity
takeoff, cost estimating, resource leveling, or a reconciliation editor. Those
capabilities remain later work and must enter through the same
`ProjectImportDraft` contract.

## Non-negotiable implementation rules

- Gemini interprets source content. It never supplies canonical IDs, authorization,
  confirmation, write tokens, or trusted provenance metadata.
- The Project Ingestion Service owns the bounded extraction pipeline, durable
  import-job lifecycle, validation lifecycle, review state, and commit boundary.
- Deterministic services own normalization, validation, state transitions,
  canonical IDs, duplicate detection, authorization, transactions, and retries.
- Firestore is the source of truth for sources, import state, drafts, canonical
  records, claims, provenance, and activity.
- Every state-changing operation is idempotent and atomically emits its required
  `ActivityEvent`.
- A conflict always blocks server-side confirmation. The UI is never the safety
  boundary.
- A second import cannot silently duplicate or replace canonical project truth.
- Initial inventory remains observed truth; material requirements remain planned
  truth.
- Purchases and external actions remain approval-gated after initialization.
- Source text, prompts, model output, secrets, and chain-of-thought are not logged.

## Current gaps to close

The implementation must not be called complete while any of these remain:

- material shortage evaluation totals unrelated active-task requirements;
- Phase 18 tests fail and do not execute the operational acceptance scenario;
- the live Gemini script prints output without asserting the contract;
- import-specific tracing, metrics, and diagnostic logging are absent;
- project-initialization status claims currently exceed the passing evidence.

## Target architecture

### New Project and setup routing

Use dedicated, reload-safe routes rather than keeping the complete journey in the
current modal:

```text
/projects/new
    file-first import entry or manual-details fallback

/projects/{project_id}/setup
    source entry, extraction recovery, latest-import recovery, or manual setup

/projects/{project_id}/imports/{import_id}
    read-only review, persisted-source retry, and confirm/cancel decision
```

The existing New Project entry points must navigate to `/projects/new`. The wizard
must generate and retain stable idempotency keys for project creation and import
creation. `api.createProject` must accept the caller's stable key rather than create
a new key on every retry.

After project creation, immediately replace the URL with the project-scoped setup
route. A reload, timeout, or extractor outage must therefore recover the same
project and latest import instead of creating duplicates.

### Setup methods

The first screen starts with the recommended import path. It does not ask users
to retype project details that can be extracted from their file. Manual project
details remain an explicit fallback for users without an importable source:

1. **Import an existing plan** — recommended; accepts pasted text, `.txt`,
   `.md`, `.docx`, `.xlsx`, `.xls`, `.csv`, or text-based `.pdf` content and
   enters extraction/review. Google Docs are imported after export to `.docx`
   or `.pdf`.
2. **Start with an empty project** — continues to existing manual task/material
   setup and leaves readiness derived as `PARTIALLY_CONFIGURED` until tasks exist.

File-first onboarding derives only a temporary shell name from the source file so
the existing project-scoped authorization and recovery boundaries remain intact.
The reviewed extracted project name, location, description, dates, and status
replace that shell metadata only inside the first confirmed import transaction.
Later additive imports cannot rename an already-populated project.

Selecting local text/Markdown reads text in the browser. Office documents, CSV,
and PDF retain their encoded bytes through the caller-owned retry claim and are
parsed by bounded server-side adapters before entering the same normalized text,
direct Gemini extraction, review, and confirmation lifecycle. Archive expansion,
page, row, cell, raw-file, and extracted-text limits are enforced before model
invocation. BIM, Primavera, and MS Project remain rejected.

### Durable import lifecycle

Persist and enforce this state machine:

```text
UPLOADED
    ↓ claim extraction
EXTRACTING
    ↓ schema-constrained candidate accepted
DRAFT
    ↓ claim deterministic validation
VALIDATING
    ├── blocking errors → VALIDATION_FAILED
    └── reviewable draft → NEEDS_REVIEW
                              ├── cancel → CANCELLED
                              └── confirm claim → CONFIRMED
                                                     ↓ claim commit
                                                 IMPORTING
                                                     ├── failure → IMPORT_FAILED
                                                     └── success → IMPORTED

EXTRACTING → EXTRACTION_FAILED
```

Rules:

- every transition has an allowlisted predecessor set and optimistic version;
- the same transition claim replays without another side effect;
- a different key or payload fingerprint conflicts;
- leases apply only while work is actively executing;
- dependency unavailability transitions immediately to `EXTRACTION_FAILED` with a
  safe code and retryable record;
- schema and cross-reference failures preserve the draft/candidate needed for
  diagnosis and retry;
- confirmation first persists `CONFIRMED`, then invokes the deterministic importer;
  a crash between those steps is resumed by the exact confirmation claim;
- cancellation is unavailable after a commit claim reaches `CONFIRMED` or
  `IMPORTING`;
- terminal records retain source/import identity and bounded failure information.

`ProjectImport` is the durable import job. It persists `id`, `project_id`,
`source_id`, `status`, `extraction_attempt`, `schema_version`, `model`, `draft`,
`warnings`, `conflicts`, `created_at`, `updated_at`, `confirmed_at`, `imported_at`,
`error_code`, and version-bound extraction retry claims directly or through the
versioned draft/diagnostic fields. A
worker restart resumes the exact persisted import claim; no ADK session or
invocation state participates in recovery.

### Validation boundary

Pydantic contracts validate individual field shapes and bounds. Cross-entity rules
belong exclusively to `ProjectImportValidator`, including:

- duplicate phase, task, material, and milestone temporary IDs;
- unknown phase, predecessor, successor, task, and material references;
- self-dependencies, duplicate edges, and cycles;
- duplicate normalized task/material candidates;
- invalid or unresolved dates without inferred month/year;
- task date order and completed-state evidence;
- canonical and compatible units;
- non-negative opening inventory and positive requirement quantities;
- duplicate task/material requirements;
- existing canonical-state conflicts;
- exact transaction write-plan and document-size bounds.

Validation returns warnings and blocking conflicts as typed data. It does not throw
away the draft for expected user-correctable input. `validate_or_raise` and the
confirmation service must reject both newly detected errors and every persisted
blocking conflict.

### Duplicate and re-import policy

Full changed/removed reconciliation remains deferred. V1 supports safe additive
imports only:

- compare the validated draft against current authorized canonical tasks,
  materials, dependencies, and requirements before review;
- classify exact new entities as `ADDED`;
- classify normalized identity matches, changed requirements, and ambiguous matches
  as blocking `CHANGED` or `CONFLICTED` results;
- do not infer or apply removals in V1;
- rerun the preflight inside the commit transaction to close the concurrency gap;
- exact replay of the same confirmed import remains a no-op;
- a distinct import may add genuinely new entities but may not duplicate or replace
  existing truth without a future reconciliation workflow.

### Trusted provenance

The application constructs trusted provenance from the persisted `ProjectSource`.
Gemini may identify only source-local locators such as section or external row label.

Every created phase, task, milestone, dependency relationship, material, opening
inventory entry, and material requirement must be traceable to:

- project ID;
- import ID;
- source ID and checksum;
- canonical target entity type and ID, or a typed dependency relationship key;
- trusted source type and name from `ProjectSource`;
- optional extracted section/external reference;
- importing actor and timezone-aware timestamp.

Extend the generic provenance contract with target identity rather than creating a
different provenance model per entity. Where a draft fact has no precise source
locator, synthesize an import-level provenance record instead of omitting traceability.
Do not persist model-supplied source names, types, IDs, or timestamps as trusted data.

### Exact commit planning

Build an immutable prepared mutation plan before confirmation. Its write count must
include:

- import record transitions included in the commit transaction;
- phases;
- regular tasks and milestone tasks;
- material records;
- opening ledger entries;
- material requirements;
- provenance records;
- task, dependency, material, requirement, and lifecycle activities.

The validator must reject a draft before confirmation when the exact plan exceeds
the configured safe Firestore transaction budget or serialized document limits.
Keep the V1 commit atomic; do not silently split a project import across partially
successful batches.

### Operational material reasoning

Shortage evaluation must use the material requirements linked to the resolved focus
tasks, not every active task in the project.

```text
resolved focus task IDs
    ↓
requirements for those tasks and material
    ↓
required quantity in canonical unit
    ↓
required quantity - available net stock
    ↓
one guarded request and pending approval when shortage > 0
```

If no task focus or applicable requirement can be resolved, update safely reported
inventory but do not manufacture a project-wide requirement. Return clarification or
a bounded risk observation. Completed and cancelled tasks do not contribute. The
material request's affected task IDs must exactly match the requirements used in the
calculation.

### API recovery contract

Keep the existing create/get/confirm/cancel routes and add a bounded project-scoped
way for setup UI to recover the latest import, for example:

```text
GET /projects/{id}/imports?limit=10&status=...
```

Requirements:

- create-import exact replay returns the same import and current state;
- list/get never expose source text unless a separately authorized source endpoint
  is intentionally added;
- response models expose safe failure code, retryability, timestamps, counts, and
  current optimistic version;
- conflict details are sufficient for human review but contain no raw model internals;
- all routes require active project membership; create, confirm, cancel, and retry
  require project-management permission;
- rate-limit extraction by actor and project because it invokes a billed model;
- all sync/async handler choices must pass ASGI integration without thread-pool
  starvation or hanging requests.

### Observability contract

Add one trace rooted at import creation with spans for:

```text
source.persist
import.extract
import.schema_validate
import.normalize
import.validate
import.review_wait
import.confirm
import.commit
```

Structured logs include `project_id`, `import_id`, `source_id`, trace ID, status,
extraction/import attempt, duration, schema version, prompt/model registry key,
validation outcome, and commit outcome. IDs belong in log fields, not metric labels.

Metrics use bounded labels and cover:

- imports started, reviewed, cancelled, confirmed, imported, and failed;
- extraction, validation, review-wait, and commit duration;
- validation conflict/warning counts by allowlisted code;
- extraction retry and lease recovery counts;
- commit write-plan size.

Never log source contents, model response bodies, prompts, credentials, or private
reasoning.

## Ordered implementation tasks

### PI-00 — Correct the baseline and lock regression fixtures

**Status:** complete locally on 2026-08-19. The focused suite records 22 passing
tests and seven strict expected failures, one for each audited implementation
gap. Ruff check/format and documentation validation pass.

**Work**

- [x] Change Project Initialization completion claims in `tasks/plan.md`,
  `tasks/todo-v1.md`, and `STATUS.md` to partial until this plan's gates pass.
- [x] Repair invalid IDs, wrong project lookups, stale activity assertions, lint
  failures, and the hanging review API regression without weakening assertions.
- [x] Add failing regression tests for conflict confirmation, extractor outage,
  validation-state preservation, duplicate second import, write-budget counting,
  provenance linkage, and task-specific shortage calculation.

**Acceptance**

- [x] Each audited defect has a focused red test that fails for the intended reason.
- [x] No test claims operational integration by inspecting setup data alone.
- [x] Baseline documentation distinguishes implemented code from passing evidence.

**Verification**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_project_import_service.py \
  tests/unit/test_project_import_validation.py \
  tests/integration/test_project_import_review_api.py \
  tests/integration/test_phase18_operational.py
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

### PI-01 — Make validation reviewable and deterministic

**Depends on:** PI-00

**Status:** complete locally on 2026-08-19. Structurally valid but internally
inconsistent drafts now survive extraction, persist as `VALIDATION_FAILED` with
typed conflicts, and are rejected by both the review endpoint and the direct
import service before canonical writes. The focused verification suite passes
24 tests with only the PI-02 and PI-05 strict expected failures remaining.

**Work**

- [x] Remove cross-entity reference and duplicate checks from the Pydantic envelope.
- [x] Make `ProjectImportValidator` the only owner of complete-draft validation.
- [x] Persist typed warnings and blocking conflicts without losing the draft.
- [x] Reject all persisted conflicts at the server confirmation boundary.

**Acceptance**

- [x] Unknown references, duplicate IDs, bad dependencies, and incompatible units
  reach `VALIDATION_FAILED` with a preserved draft.
- [x] Warnings may reach review; every blocking conflict prevents canonical writes.
- [x] Direct API confirmation and UI confirmation enforce the same policy.

**Verification**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_project_import_contracts.py \
  tests/unit/test_project_import_validation.py \
  tests/integration/test_project_import_review_api.py
```

### PI-02 — Implement the durable lifecycle and recovery claims

**Depends on:** PI-01

**Status:** complete locally on 2026-08-19. The explicit transition table is
enforced at every import mutation, extraction failures persist safe diagnostics,
and exact request claims resume from failed/expired extraction and confirmed
commit stages. The required extraction-service/API suite passes 20 tests; two additional
restart tests pass against the Firestore emulator with fresh repository clients.

**Work**

- [x] Define and test the complete transition table.
- [x] Persist `UPLOADED`, `EXTRACTING`, `DRAFT`, `VALIDATING`, `NEEDS_REVIEW` or
  `VALIDATION_FAILED`, `CONFIRMED`, `IMPORTING`, and terminal state transitions.
- [x] Move extractor dependency failure inside guarded failure handling.
- [x] Resume expired or failed extraction and confirmed commit claims idempotently.

**Acceptance**

- [x] Every failure leaves a coherent, reloadable import record with safe diagnostics.
- [x] Exact retries continue the same import; mismatched retries conflict.
- [x] Restart between lifecycle stages resumes or terminates safely, including
  fresh-client Firestore recovery from persisted draft and import claims.

**Verification**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_project_import_extraction.py \
  tests/integration/test_project_import_review_api.py
FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 \
  .venv/bin/python -m pytest -q \
  tests/integration/test_project_import_lifecycle_firestore.py
```

The Firestore command must run against a local emulator.

### PI-03 — Make provenance trusted and complete

**Depends on:** PI-01

**Work**

- [x] Add canonical target identity and source checksum to import provenance.
- [x] Construct trusted source metadata from `ProjectSource`, not Gemini output.
- [x] Link or synthesize provenance for every imported canonical fact and opening
  inventory entry.
- [x] Make user-facing “Why does OG know this?” queries resolve source/import links.

**Acceptance**

- [x] Every canonical record created by import resolves to its project, import, and
  source without parsing an ID string.
- [x] Forged model source metadata cannot alter trusted provenance.
- [x] Cross-project provenance lookup fails at API and repository boundaries.

**Verification**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_project_import_service.py \
  tests/unit/test_project_import_provenance.py \
  tests/integration/test_project_import_provenance_api.py
FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 \
  .venv/bin/python -m pytest -q \
  tests/integration/test_firestore_repositories.py \
  tests/integration/test_authorization.py
```

The Firestore command must run against a local emulator.

### PI-04 — Add safe additive-import preflight

**Depends on:** PI-01, PI-03

**Status:** complete locally on 2026-08-19. Deterministic review preflight now
compares phases, tasks/milestones, dependencies, materials/aliases, and
task-material requirements with authorized canonical truth. All reconciliation
operations block in V1, and the same preflight is rerun inside the canonical
commit transaction.

**Work**

- [x] Replace the all-`ADDED` diff stub with deterministic canonical preflight.
- [x] Detect normalized task/material duplicates and changed requirements.
- [x] Rerun preflight inside the commit transaction.
- [x] Block changed, removed, or ambiguous reconciliation in V1 with an explicit
  safe conflict instead of silently applying it.

**Acceptance**

- [x] Exact import replay is a no-op.
- [x] A second import of the same logical plan creates zero canonical duplicates.
- [x] A second import containing only genuinely new entities can be reviewed and
  committed without modifying existing entities.

**Verification**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_project_import_diff.py \
  tests/unit/test_project_import_service.py
```

### PI-05 — Count and commit the exact mutation plan

**Depends on:** PI-02, PI-03, PI-04

**Work**

- [x] Introduce one prepared mutation-plan type shared by validation and commit.
- [x] Count every canonical, provenance, ledger, import-state, and activity write.
- [x] Enforce transaction and document-size safety before confirmation.
- [x] Correct entity types and source/import metadata on creation activities.

**Acceptance**

- [x] The count asserted by tests equals the writes attempted by the transaction.
- [x] Oversized drafts remain reviewable but cannot be confirmed.
- [x] Commit failure produces `IMPORT_FAILED` with no partial canonical state.

`PreparedProjectImportPlan` is immutable and owns deterministic canonical IDs,
provenance targets, and exact canonical/activity/import-state write counts. The
default safety policy reserves Firestore headroom with a 450-write transaction
limit and a conservative 750,000-byte document estimate; validation persists a
typed conflict while retaining the complete review draft when either bound is
exceeded.

**Verification**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_project_import_service.py \
  tests/integration/test_firestore_repositories.py
```

### Backend checkpoint — canonical import safety

- [x] PI-00 through PI-05 acceptance criteria pass.
- [x] In-memory and Firestore-backed exact replay produce identical outcomes.
- [x] Conflict, concurrency, timeout, restart, and commit-failure cases leave no
  duplicate or partial canonical state.
- [x] Ruff, format, mypy, and documentation checks pass.

### PI-06 — Build the New Project setup route

**Depends on:** PI-00

**Work**

- [x] Replace the New Project modal-only path with `/projects/new`.
- [x] Begin with direct project-file import and expose the complete validated
  project-details form only as the manual fallback.
- [x] Keep the project-creation idempotency key stable across retries.

**Acceptance**

- [x] Every New Project entry point begins the same wizard.
- [x] A timeout/retry creates exactly one project.
- [x] Successful creation immediately establishes a reload-safe project setup URL.

Completed locally on 2026-08-19 and made file-first on 2026-08-21. The wizard
persists its bounded source/manual draft and caller-owned creation claim in
session storage, restores them after reload, and replaces the browser location with
`/projects/{project_id}/setup?method=import|empty` as soon as creation succeeds.
The additive create-project API persists description, dates, and status; exact
Firestore replay returns one project and one activity, while a mismatched replay
is rejected. Desktop and mobile Chromium exercise the committed-response-loss
case and pass the wizard's WCAG A/AA scan. Structured source entry is completed
by PI-07 below.

**Verification**

```bash
cd frontend
npm test -- projects
npm run lint
npm run typecheck
```

### PI-07 — Connect structured source entry to import creation

**Depends on:** PI-02, PI-06

**Work**

- [x] Add typed `createProjectImport` and bounded import-list/latest APIs to the
  frontend client.
- [x] Build direct `.txt`/`.md`/`.docx`/`.xlsx`/`.xls`/`.csv`/`.pdf` selection
  in `/projects/new`, stage the source through project creation, and retain
  source paste/editing in `/projects/{id}/setup`.
- [x] Preserve the import idempotency claim across timeout, reload, and retry.
- [x] Recover the latest nonterminal import and route to its current state.

**Acceptance**

- [x] A user can start extraction from New Project without copying an import ID or
  entering a hidden URL.
- [x] Project-created/import-failed state is explicit and retryable.
- [x] Unsupported file types are rejected before model invocation.

Completed locally on 2026-08-19 and extended on 2026-08-21. `/projects/new`
accepts local text, Markdown, Word, Excel, CSV, and text-based PDF files without
manual transcription and stages the source into the project-scoped setup route.
The import path does not request project metadata first: confirmation atomically
applies the reviewed extracted metadata to the initial project shell. The review
screen displays those values before the user decides.
That route also accepts pasted text, retains the source plus caller-owned import
claim through response loss and reload, and recovers the latest nonterminal
server record without a copied import ID. Recovery uses a bounded, authorized
summary feed that excludes terminal records before applying its limit and never
returns source text. Unsupported adapter types are rejected at both browser and
HTTP boundaries before persistence or extraction. Desktop and mobile Chromium
exercise the committed-response-loss recovery path and the setup editor's WCAG
A/AA scan.

**Verification**

```bash
cd frontend
npm test -- project-setup project-import
npm run lint
npm run typecheck
```

### PI-08 — Harden review, decision, and terminal UI states

**Depends on:** PI-01, PI-02, PI-07

**Work**

- [x] Render lifecycle loading, validation-failed, extraction-failed, review,
  import-failed, cancelled, and imported states.
- [x] Show blocking conflicts separately from warnings and explain why confirmation
  is disabled.
- [x] Add stable retry/cancel/confirm actions with optimistic-version recovery.
- [x] Return imported users to the initialized overview and cancelled users to setup.

**Acceptance**

- [x] Reloading any setup/review URL reconstructs state from the API.
- [x] Double-click, stale version, timeout, and exact replay create one decision.
- [x] Keyboard, screen-reader, 360 px, and desktop journeys remain usable.

Completed locally on 2026-08-21. The review route now renders every durable
lifecycle category from the authorized API, polls active work, separates blocking
conflicts from warnings, and preserves confirm/cancel claims in session storage so
response loss and reload reuse the exact server decision. A synchronous in-flight
guard suppresses rapid duplicate clicks, optimistic conflicts reload the latest
version, successful initialization refreshes the project snapshot before routing,
and cancellation returns to import setup. Horizontally scrollable review tables
are keyboard focusable at mobile widths.

Focused component/setup verification passes 26 tests with ESLint and TypeScript
clean. Production-build Playwright passes four real-API/Firestore journeys across
desktop Chromium and a 360 px mobile viewport: confirm and cancel both recover
from committed response loss, confirmation produces one copy of each imported
task in the refreshed snapshot, keyboard order is correct, and the review has no
WCAG A/AA violations in the scanned state.

**Verification**

```bash
cd frontend
npm test -- project-import-review project-setup
npm run test:e2e -- project-initialization.spec.ts
```

### Frontend checkpoint — New Project to initialized project

- [x] New Project → Import existing plan → Review → Confirm works through real APIs.
- [ ] New Project → Start empty reaches manual setup and honest readiness.
- [ ] Extraction failure, validation failure, cancellation, and commit retry are
  covered in browser tests.
- [x] No browser fixture or hard-coded import ID supplies production screen state.

### PI-09 — Correct task-specific material reasoning

**Depends on:** PI-05

**Work**

- [x] Resolve applicable requirements from the current focus task set.
- [x] Remove the all-active-task aggregate fallback from shortage requests.
- [x] Bind request quantities and affected task IDs to the requirements used.
- [x] Preserve safe inventory updates when requirement context is missing.

**Acceptance**

- [x] Plastering requiring 100 bags with 10 on hand produces a 90-bag request.
- [x] Changing that requirement to 80 produces a 70-bag request.
- [x] An unrelated task's cement requirement does not change either result.

**Verification**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_material_tools.py \
  tests/integration/test_phase18_operational.py \
  tests/integration/test_worker_site_update.py
```

### PI-10 — Prove imported dependencies and ongoing material evolution

**Depends on:** PI-04, PI-09

**Work**

- [x] Exercise blocker impact using imported dependency records only.
- [x] Repeat after removing the dependency in an isolated fixture and prove the
  downstream claim disappears.
- [x] Prove typed operational material auto-creation coexists with imported state.

**Acceptance**

- [x] Dependency impact changes only when canonical graph data changes.
- [x] New operational materials use canonical units, ledger entries, activity, and
  idempotency without invoking project re-import.

**Verification**

```bash
.venv/bin/python -m pytest -q \
  tests/integration/test_phase15.py \
  tests/integration/test_phase18_operational.py \
  tests/integration/test_worker_site_update_firestore.py
```

### PI-11 — Add import observability and bounded diagnostics

**Depends on:** PI-02, PI-05

**Work**

- [x] Add import spans, metrics, structured logs, and persisted trace correlation.
- [x] Record model/prompt registry keys, durations, validation outcome, and commit
  outcome without source content.
- [x] Add safe user-visible failure codes and operator-facing diagnostic fields.
- [x] Add alert/runbook coverage for stuck extraction, repeated failure, and commit
  failure.

**Acceptance**

- [x] One trace follows source through extraction, validation, review, and commit.
- [x] A failed import is diagnosable from IDs without reading confidential content.
- [x] Metrics use bounded labels and logs contain no prompt, source, or model body.

**Verification**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_observability.py \
  tests/integration/test_observability.py
.venv/bin/python scripts/smoke_observability.py
```

### PI-12 — Complete security and abuse controls

**Depends on:** PI-02, PI-03, PI-07

**Work**

- [x] Test authentication, active membership, `MANAGE` permission, project scope,
  source scope, import scope, confirmation scope, and provenance scope.
- [x] Add bounded source/file validation and per-user/project extraction rate limits.
- [x] Treat project source contents as untrusted data inside the extraction prompt.
- [x] Verify model output cannot supply canonical identity, trusted provenance,
  mutation tokens, or decision authority.

**Acceptance**

- [x] Project A cannot list, read, retry, cancel, confirm, or trace Project B data.
- [x] Prompt-injection text can only affect draft content inside the schema boundary.
- [x] Oversized, invalid, or rate-limited requests perform no model or canonical write.

**Verification**

```bash
.venv/bin/python -m pytest -q \
  tests/integration/test_authorization.py \
  tests/integration/test_api_errors_limits.py \
  tests/integration/test_project_import_review_api.py
```

### PI-13 — Replace placeholder evaluation with release evidence

**Depends on:** PI-01 through PI-12

**Work**

- [x] Replace `scripts/eval_phase19.py` printing with assertions and a versioned
  evaluation artifact.
- [x] Add structured, imperfect Markdown, typo, missing-date, ambiguous-requirement,
  prompt-injection, and canonical-ID-forgery cases.
- [ ] Run the complete Ridge House production acceptance scenario through project
  creation, import, review, operational update, and approval.
- [x] Add Firestore refresh, sign-out/in, API restart, worker restart, concurrency,
  and exact replay gates.

**Acceptance**

- [x] Live Gemini maps plastering/cement/100/bags to draft references and quantity.
- [x] “Foundation due on the 19th” produces an unresolved-date warning and no date.
- [x] Deterministic code alone supplies canonical IDs and commits.
- [x] The complete scenario derives 90, then 70 after the requirement fixture changes.

**Verification**

Store live evaluation output under an ignored or approved evidence location with
model ID, prompt version, timestamp, commit SHA, and pass/fail assertions. A printout
or manually inspected response is not a passing gate.

### PI-14 — Release, rollback, and documentation closure

**Depends on:** PI-13

**Work**

- [x] Update API, domain model, ingestion, security, operations, and traceability docs.
- [x] Amend ADR-001 for the corrected direct-Gemini ingestion boundary; no new
  workflow runtime or ADR is required.
- [x] Add deployment smoke and rollback checks for project creation/import/recovery.
- [x] Update status and task checklists only from passing recorded evidence.

**Acceptance**

- [ ] Clean checkout installs, checks, tests, builds, and browser journeys pass.
- [ ] Staging proves authenticated New Project through initialized operational state.
- [ ] Rollback preserves already-created projects, sources, imports, canonical data,
  provenance, and activities.
- [x] Known limitations have owners and do not contradict V1 acceptance.

## Final verification gate

Run from a clean checkout with documented dependencies:

```bash
uv sync --all-extras --locked
.venv/bin/python -m pytest -q -m "not backing_services"
.venv/bin/python -m pytest -q -m backing_services
.venv/bin/python -m pytest -q tests/production_readiness
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/python scripts/check_docs.py

cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

Project Initialization is complete only when all commands pass and the following
browser/API/Firestore-backed scenario is recorded:

1. An administrator selects **New Project**.
2. They create Ridge House and choose **Import an existing plan**.
3. They paste the accepted structured-text fixture.
4. OG persists the source and import, extracts through the direct Gemini service,
   and shows review.
5. The user sees the exact tasks, dependencies, materials, requirements, opening
   inventory, warnings, and conflicts before mutation.
6. Confirmation creates canonical state once with complete provenance and activity.
7. Reload and sign-out/in show the same initialized project.
8. The canonical site update produces blockwork completion, electrical blocker,
   plastering risk, cement stock of 10, shortage of 90, and one pending approval.
9. Exact replay produces no additional mutation, request, approval, notification,
   provenance, or activity.
10. The equivalent fixture with an 80-bag requirement produces a 70-bag shortage.
11. Cross-project access, conflicted confirmation, duplicate second import, and
    restart/concurrency attempts fail safely.

## Definition of done

- [ ] The New Project journey visibly includes import from its first setup decision.
- [ ] Manual empty-project setup remains available and honest about readiness.
- [ ] The complete durable import lifecycle is persisted and recoverable.
- [ ] Expected validation errors preserve a reviewable draft.
- [ ] Blocking conflicts cannot be confirmed through any boundary.
- [ ] Exact replay is a no-op and distinct imports cannot duplicate canonical truth.
- [ ] Every imported fact has trusted canonical provenance.
- [ ] The exact write plan is validated before confirmation.
- [ ] Initial task state and inventory persist without fabricated history.
- [ ] Imported requirements drive task-specific shortages.
- [ ] Imported dependencies drive graph-specific risk.
- [ ] Extraction, validation, review, commit, failure, and retry are observable.
- [ ] Project/source/import/provenance access is tenant-isolated.
- [ ] Live model evaluation asserts structured extraction and date ambiguity safety.
- [ ] Backend, backing-service, frontend, browser, eval, and production-readiness
  gates all pass from a clean checkout.
- [ ] `STATUS.md`, `tasks/plan.md`, and `tasks/todo-v1.md` report only evidence
  that was actually rerun and recorded.
