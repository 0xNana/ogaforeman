# OG Foreman — Project Initialization & Operational Baseline Implementation Plan

## 1. Objective

Build OG Foreman’s production-grade **Project Initialization System**.

Its job is to turn a contractor’s existing project information into the canonical operational model that OG uses throughout the life of the project.

The initialized model must give OG enough trusted context to answer:

* What work exists?
* What should happen next?
* What depends on what?
* What materials does each activity require?
* What quantities are currently available?
* What work is already complete/in progress?
* What is late, blocked, or at risk?
* What changed when a new site event arrives?
* What action should happen next?

The system must support:

```text
PROJECT SOURCES
      ↓
AI EXTRACTION
      ↓
DRAFT PROJECT MODEL
      ↓
DETERMINISTIC VALIDATION
      ↓
HUMAN REVIEW
      ↓
CANONICAL PROJECT MODEL
      ↓
ONGOING SITE EVENTS
      ↓
OG COORDINATION
```

The implementation must be extensible to additional V2 data sources without replacing the canonical project model or import lifecycle.

---

# 2. Architecture Principle

OG operates on two classes of truth.

## Planned Truth

Defines what should happen.

Examples:

* tasks
* dates
* dependencies
* milestones
* material requirements
* planned quantities
* assignments

## Observed Truth

Defines what is actually happening.

Examples:

* voice updates
* photos
* task completion reports
* current inventory
* deliveries
* blockers
* delays
* approvals

OG continuously reconciles:

```text
PLANNED TRUTH
      +
OBSERVED TRUTH
      ↓
DEVIATION
      ↓
NEXT ACTION
```

Example:

```text
Planned:
Ground-floor plastering requires 100 bags cement.

Observed:
10 bags on site.

Deterministic result:
Shortage = 90 bags.

OG:
Plastering is at risk.
Prepare a 90-bag material request.
```

Gemini must not invent the 100-bag requirement.

---

# 3. Responsibility Boundaries

## Gemini extraction

Responsible for:

* document/text interpretation
* extracting candidate project facts
* understanding natural language
* resolving semantic relationships
* identifying likely tasks/materials/dependencies
* generating typed draft structures
* producing schema-constrained candidate facts from untrusted source content

Gemini is called directly through the Google Gen AI / Vertex model API for this
bounded transformation. Use of Gemini alone does not require an agent runtime.

## Project Ingestion Service

Owns:

* source loading and bounded input handling
* direct Gemini extraction calls
* import-job claims, attempts, failures, and restart recovery
* draft assembly and handoff to deterministic normalization and validation
* review state and deterministic commit boundary

## Deterministic application code

Responsible for:

* validation
* canonical IDs
* normalization
* duplicate detection
* date validation
* unit validation
* dependency validation
* material requirement validation
* permissions
* concurrency
* idempotency
* commit/rollback
* versioning

## Firestore

Authoritative store for:

* project
* tasks
* dependencies
* materials
* material requirements
* actual inventory
* approvals
* issues
* activity
* import records
* source provenance

## Google ADK

Owns:

* agent/workflow orchestration
* operational workflows
* HITL interruption/resume
* session/runtime continuity

ADK is not used for project initialization. It remains the runtime for OG's
autonomous, event-driven, conversational, tool-using, and resumable operations.

---

# 4. Canonical Domain Model

Project Initialization must map every source into one canonical contract.

## ProjectImportDraft

```text
ProjectImportDraft
├── id
├── project_id
├── source_id
├── status
├── project
├── phases[]
├── tasks[]
├── dependencies[]
├── materials[]
├── material_requirements[]
├── milestones[]
├── warnings[]
├── conflicts[]
├── unresolved_references[]
├── created_at
├── reviewed_at
└── confirmed_at
```

---

# 5. Project Draft

Minimum:

```text
ProjectDraft
├── name
├── description
├── type
├── location
├── start_date
├── target_end_date
└── status
```

Do not require every field for import.

Required minimum:

* name

---

# 6. Phase Draft

```text
PhaseDraft
├── temp_id
├── name
├── sequence
└── description
```

Examples:

* Site Preparation
* Substructure
* Superstructure
* Services
* Finishes
* Closeout

---

# 7. Task Draft

```text
TaskDraft
├── temp_id
├── name
├── description
├── phase_temp_id
├── planned_start
├── planned_finish
├── duration
├── initial_status
├── location
├── trade
├── assignee_reference
└── source_reference
```

`temp_id` is draft-only.

Gemini must never generate canonical task IDs.

---

# 8. Dependency Draft

```text
DependencyDraft
├── predecessor_temp_id
├── successor_temp_id
├── type
└── source_reference
```

V1 may support only Finish-to-Start internally.

Do not build a full scheduling engine simply because other dependency types exist.

The data contract may leave room for them.

---

# 9. Material Draft

```text
MaterialDraft
├── temp_id
├── name
├── canonical_unit
├── initial_on_hand_quantity
├── location
└── source_reference
```

Inventory must remain separate from requirements.

---

# 10. Material Requirement Draft

This is a core entity.

```text
MaterialRequirementDraft
├── task_temp_id
├── material_temp_id
├── required_quantity
├── unit
├── required_by
├── source_reference
└── confidence
```

This relationship allows OG to reason:

```text
Task
→ requires
→ Material
→ Quantity
```

Do not store only:

```text
Cement = 100 bags
```

Store:

```text
Ground-floor plastering
→ Cement
→ 100 bags
```

---

# 11. Source Provenance

Every imported project fact must be traceable.

Implement:

```text
SourceReference
├── source_id
├── source_type
├── source_name
├── section
├── external_reference
└── imported_at
```

Example:

```text
Task:
Ground-floor plastering

Source:
project-plan.md
section: "Finishes"

Material requirement:
100 bags Cement

Source:
project-plan.md
section: "Ground-floor plastering / Materials"
```

This enables future answers such as:

> Why does OG say plastering needs 100 bags?

Without provenance, AI-derived project state becomes difficult to trust.

---

# 12. Import Source Abstraction

Do not couple initialization to pasted Markdown.

Create:

```text
ProjectSourceAdapter
```

Contract:

```text
load()
normalize_input()
extract()
return ProjectImportDraft
```

V1 adapter:

```text
StructuredTextProjectAdapter
```

Future:

```text
CsvScheduleAdapter
SpreadsheetProjectAdapter
BoqAdapter
PdfProjectAdapter
PrimaveraAdapter
MsProjectAdapter
ExternalPmsAdapter
```

Only implement the first adapter now.

The architecture must permit the others without changing the canonical domain model.

---

# 13. Import Lifecycle

Implement a durable import state machine.

```text
UPLOADED
    ↓
EXTRACTING
    ↓
DRAFT
    ↓
VALIDATING
    ↓
NEEDS_REVIEW
    ↓
CONFIRMED
    ↓
IMPORTING
    ↓
IMPORTED
```

Failure states:

```text
EXTRACTION_FAILED
VALIDATION_FAILED
IMPORT_FAILED
CANCELLED
```

Do not use model chat history as import state.

Persist the import record.

---

# PHASE 0 — Domain Audit

## Goal

Determine what already exists before adding new models.

Inspect:

* Project
* Task
* dependency representation
* Material
* MaterialRequirement if existing
* Issue
* DailyLog
* ActivityEvent
* repository structure
* domain services
* ADK workflows
* canonical ID generation
* versioning
* transaction support

Document:

```text
internal-docs/PROJECT_INITIALIZATION_ARCHITECTURE.md
```

For each required concept mark:

```text
EXISTS
EXTEND
CREATE
```

## Gate

No new implementation until the canonical model is mapped onto the existing domain.

---

# PHASE 1 — Canonical Import Contracts

Implement Pydantic/domain contracts for:

```text
ProjectImportDraft
ProjectDraft
PhaseDraft
TaskDraft
DependencyDraft
MaterialDraft
MaterialRequirementDraft
SourceReference
ImportWarning
ImportConflict
```

Requirements:

* schema version
* strict types
* no arbitrary IDs from Gemini
* explicit units
* explicit dates
* optional source references

Example:

```text
schema_version = 1
```

## Gate

A complete residential project fixture validates using only application code.

No Gemini required.

---

# PHASE 2 — Deterministic Validation

Implement:

```text
ProjectImportValidator
```

Validation rules:

### Tasks

* unique temp IDs
* usable names
* valid dates
* start <= finish where both exist

### Dependencies

* predecessor exists
* successor exists
* no self-dependencies
* obvious duplicate edges rejected
* detect cycles before import

### Materials

* valid name
* valid canonical unit
* quantity >= 0

### Material requirements

* referenced task exists
* referenced material exists
* quantity > 0
* requirement unit compatible with material unit

### Dates

Never invent missing month/year in deterministic validation.

Represent unresolved dates as warnings requiring review.

## Gate

Invalid drafts fail before any canonical record is written.

---

# PHASE 3 — Deterministic Importer

Implement:

```text
ProjectImportService
```

Responsibilities:

1. require validated draft
2. require user confirmation
3. generate canonical IDs
4. create phases
5. create tasks
6. map temporary IDs
7. create dependencies
8. create materials
9. create material requirements
10. establish initial task state
11. establish initial inventory
12. persist provenance
13. create ActivityEvents
14. mark import complete

Prefer transaction/batch semantics where supported.

At minimum:

* validate everything before writes
* make import idempotent
* prevent accidental duplicate commits

## Gate

Importing the same confirmed import twice does not duplicate project state.

---

# PHASE 4 — Source Persistence

Create a first-class source record.

```text
ProjectSource
├── id
├── project_id
├── type
├── filename/name
├── checksum
├── storage_reference
├── created_by
├── created_at
└── status
```

For pasted text, persist:

* source text or durable storage reference
* checksum

This allows:

* provenance
* reprocessing
* future diffing
* auditing

## Gate

Every imported record can be traced to an import/source.

---

# PHASE 5 — Structured Text Adapter

Implement one production-quality ingestion adapter:

```text
StructuredTextProjectAdapter
```

Accepted V1 input:

* pasted text
* Markdown
* OG template format

Do not make exact formatting mandatory.

The adapter should accept reasonable structured variation.

Input examples:

```text
Task: Excavation
Due: 20 August 2026

Task: Foundation
Due: 24 August 2026
Depends on: Excavation

Materials:
Cement: 100 bags
```

## Gate

Adapter produces source text suitable for Gemini extraction.

---

# PHASE 6 — Gemini Project Extraction Service

Build a bounded application ingestion service that calls Gemini through the
Google Gen AI / Vertex model API with schema-constrained output.

Conceptual:

```text
persisted ProjectImport claim
      ↓
direct Gemini extraction
      ↓
schema validation
      ↓
normalize draft
      ↓
deterministic validation
      ↓
needs review
```

Gemini output:

```text
ProjectImportDraft
```

Use schema-constrained generation.

Gemini may identify:

* tasks
* material names
* quantities
* units
* dates
* dependencies
* phases

Gemini must not produce:

* Firestore IDs
* approval authority
* mutation tokens
* canonical entity IDs

## Gate

The service returns a typed `ProjectImportDraft` without constructing an ADK
`Runner`, session, invocation, workflow graph, or agent. Restart recovery uses
the persisted `ProjectImport` status, attempt, lease, draft, and error fields.

---

# PHASE 7 — Normalization Layer

Implement deterministic normalization after Gemini extraction.

Examples:

```text
pcs
piece
pieces
pices
→ pieces
```

```text
m³
m3
cubic metres
→ m3
```

Normalize task names conservatively.

Example:

```text
Ground floor plastering
Ground-floor plastering
```

may resolve as equivalent during duplicate detection.

Do not aggressively merge semantically different tasks.

## Gate

Normalization is deterministic and tested.

---

# PHASE 8 — Review API

Implement:

```text
POST /projects/{id}/imports
GET  /projects/{id}/imports/{import_id}
POST /projects/{id}/imports/{import_id}/confirm
POST /projects/{id}/imports/{import_id}/cancel
```

Exact routes may follow existing API conventions.

Review response should expose:

```text
tasks
dependencies
materials
requirements
warnings
conflicts
unresolved references
```

No mutations occur before confirmation.

## Gate

A draft can be extracted, reviewed, cancelled, and discarded without changing project truth.

---

# PHASE 9 — Review UI

Build one focused review flow.

Do not build Excel inside the browser.

Show:

## Summary

```text
20 Tasks
18 Dependencies
13 Materials
27 Requirements
2 Warnings
```

## Tasks

table

## Dependencies

simple list

## Materials

table

## Requirements

table/grouped by task

## Warnings

explicit review items

Actions:

```text
Cancel Import
Confirm & Initialize
```

If the draft is badly wrong, users cancel and correct the source.

V2 can support richer in-place editing.

## Gate

User can understand what OG is about to create before canonical state changes.

---

# PHASE 10 — Initial Actual State

Support initial status and inventory.

Task:

```text
initial_status:
PLANNED
IN_PROGRESS
COMPLETED
BLOCKED
```

Material:

```text
initial_on_hand_quantity
```

Use case:

A contractor starts OG halfway through the project.

Example:

```text
Site Clearance        COMPLETED
Excavation            COMPLETED
Foundation            IN_PROGRESS
Blockwork             PLANNED
```

Do not assume every imported project is starting from day one.

## Gate

An active project can be initialized without fabricating historical events.

---

# PHASE 11 — Project Readiness

Implement deterministic readiness.

Do not create a meaningless AI score.

Example states:

```text
EMPTY
PARTIALLY_CONFIGURED
OPERATIONAL
```

Operational requires enough structure for OG to reason usefully.

Suggested minimum:

```text
project exists
tasks exist
```

Additional capability flags:

```text
has_dependencies
has_materials
has_material_requirements
has_schedule
has_initial_state
```

OG can then answer:

> Is our project set?

with real information.

Example:

> Ridge House is operational. I have 18 tasks, 14 dependencies and material requirements for 11 tasks. Four planned activities don't have material requirements yet.

## Gate

Readiness is derived entirely from canonical data.

---

# PHASE 12 — Operational Context Queries

Ensure OG queries the newly imported model.

Examples:

```text
"Where are we with the project?"
"How about excavation?"
"What's after foundation?"
"What does plastering need?"
"How much cement does plastering require?"
"What happens if electrical slips?"
```

Responses must come from canonical state.

No generic fallback when relevant data exists.

## Gate

Entity-specific queries return entity-specific project state.

---

# PHASE 13 — Connect Imported Plan to Golden Operations

Run:

```text
Ground-floor plastering
requires 100 bags Cement

Cement on hand:
50
```

Then submit:

> We only have 10 bags left and plastering starts tomorrow.

Expected:

```text
inventory = 10
required = 100
shortage = 90
```

Then change imported requirement to:

```text
80
```

Run equivalent scenario.

Expected:

```text
shortage = 70
```

This proves OG reasons against actual project truth.

## Gate

No hardcoded/demo construction quantity affects the calculation.

---

# PHASE 14 — Dependency Reasoning

Imported project:

```text
Electrical Rough-In
   ↓
Plastering
```

Site event:

> Electrician didn't come.

Expected:

```text
Electrical Rough-In
→ BLOCKED

Plastering
→ affected/at risk according to existing scheduling policy
```

Remove that dependency.

Repeat.

Expected:

OG must no longer claim the same dependency impact.

## Gate

Schedule impact is data-driven.

---

# PHASE 15 — Material Auto-Creation During Operations

Initialization is not the only way project truth grows.

If later site operations introduce:

> 60 pieces of building wire arrived.

and Building Wire does not exist:

OG may create it through normal typed Material services where the command provides sufficient:

* material name
* quantity
* unit
* inventory semantics

This remains an operational mutation, not a project re-import.

## Gate

Initialization and ongoing project evolution coexist cleanly.

---

# PHASE 16 — Import Activity & Audit

Create user-facing events such as:

```text
project.import.started
project.import.extracted
project.import.reviewed
project.initialized
task.created
dependency.created
material.created
material.requirement.created
```

Do not spam Activity with low-level extraction internals.

Preserve:

* actor
* source
* import ID
* timestamp

## Gate

A PM can determine where initial project state came from.

---

# PHASE 17 — Re-Import Foundation

Do not implement full reconciliation yet.

But prepare the architecture.

Every import must have:

```text
source checksum
import version
created_at
source provenance
```

Canonical entities should retain source references.

Add interface:

```text
ProjectImportDiffService
```

V1 implementation may be incomplete/not user exposed.

Its future responsibility:

```text
New source
   ↓
new draft
   ↓
compare canonical project
   ↓
ADDED
CHANGED
REMOVED
CONFLICTED
```

Do not make initial import architecture impossible to diff later.

## Gate

No design assumes “projects can only ever be imported once.”

---

# PHASE 18 — Automated Tests

Required:

## Contract tests

* valid import
* missing task
* bad dependency
* cyclic dependency
* invalid material unit
* invalid quantity

## Import tests

* canonical IDs generated
* temporary IDs translated
* dependency references correct
* requirements correctly linked
* duplicate import blocked

## Gemini extraction tests

* structured project
* imperfect Markdown
* typo
* missing date
* ambiguous requirement

## Operational integration

* imported requirement drives shortage
* imported dependency drives risk
* initial inventory affects shortage
* initial completed state respected

## Persistence

* refresh
* sign out/in
* process restart

## Golden Scenario

Must remain PASS.

---

# PHASE 19 — Live Gemini Evaluation

Run billed Vertex/Gemini evaluation.

Prove:

```text
Gemini extracts:
"Plastering requires 100 bags of cement."

→ material_reference = Cement
→ task_reference = Plastering
→ quantity = 100
→ unit = bags
```

Then deterministic code owns:

```text
task_id
material_id
requirement_id
versions
write tokens
```

Include ambiguous inputs:

```text
"Foundation due on the 19th."
```

Expected:

* unresolved month/date warning
* no invented calendar date

## Gate

Live model extraction cannot directly manufacture canonical project truth.

---

# PHASE 20 — Production Failure Handling

Support:

### Extraction failure

```text
Source saved
Import = EXTRACTION_FAILED
Canonical project unchanged
Retry available
```

### Validation failure

```text
Draft preserved
Import = VALIDATION_FAILED
Canonical project unchanged
```

### Commit failure

```text
Import = IMPORT_FAILED
No false success
Retry/idempotency protected
```

### User cancellation

```text
Import = CANCELLED
Canonical project unchanged
```

Raw model/Pydantic exceptions must never become normal user UI.

## Gate

Every failure leaves the canonical project in a coherent state.

---

# PHASE 21 — Production Observability

Record:

```text
import_id
project_id
source_id
trace_id
status
extraction/import attempt
schema version
duration
model
validation result
commit result
```

Cloud Trace should allow:

```text
source
→ extraction
→ validation
→ review
→ confirmation
→ import
```

Do not log confidential source contents unnecessarily.

## Gate

Failed imports can be diagnosed from IDs and traces.

---

# PHASE 22 — Security

Enforce:

* authenticated project member
* project-scoped source access
* project-scoped imports
* project-scoped confirmation
* file/content permission checks
* no cross-project source access
* no canonical writes directly from model output

User confirming an import must have appropriate project-management permission.

## Gate

A user from Project A cannot read, confirm, or import Project B's draft.

---

# PHASE 23 — SaaS Extension Points

After V1 is stable, the architecture must support adding:

```text
CSV
Excel
PDF BOQ
MS Project
Primavera
Drawings/specifications
External PM APIs
```

Adding an adapter should mean:

```text
New adapter
    ↓
ProjectImportDraft
    ↓
same validator
    ↓
same review
    ↓
same importer
```

If adding Excel requires rewriting Task/Material initialization, this implementation has failed architecturally.

---

# V1 Shipping Scope

Production V1 includes:

```text
Project creation
Project source record
Structured-text project source
Gemini extraction
Canonical import draft
Deterministic validation
Review
Confirmation
Deterministic import
Tasks
Dates
Dependencies
Materials
Material requirements
Initial inventory
Initial task state
Provenance
Activity
Readiness
Operational integration
Tests
Observability
Security
```

---

# Explicitly Deferred

These are legitimate product features, but not part of this implementation cycle:

```text
Excel adapter
CSV adapter
PDF BOQ adapter
Primavera
MS Project
Drawing understanding
Quantity takeoff
BIM
Automatic cost estimating
Procurement marketplace
Complex schedule optimization
Resource leveling
Full import-diff/reconciliation UI
```

They are deferred because the shared ingestion architecture must be proven first.

This is sequencing, not demo limitation.

---

# Production Acceptance Scenario

Create:

**Ridge House**

Import a project plan containing:

```text
Site Clearance
Excavation
Foundation
Ground-floor Blockwork
Electrical Rough-In
Plumbing Rough-In
Ground-floor Plastering
```

Dependencies:

```text
Site Clearance
→ Excavation
→ Foundation
→ Ground-floor Blockwork

Ground-floor Blockwork
→ Electrical Rough-In

Ground-floor Blockwork
→ Plumbing Rough-In

Electrical Rough-In
→ Ground-floor Plastering

Plumbing Rough-In
→ Ground-floor Plastering
```

Materials:

```text
Cement
Sand
Blocks
Building Wire
Plumbing Pipes
```

Requirement:

```text
Ground-floor Plastering
→ Cement
→ 100 bags
```

Initial inventory:

```text
Cement
→ 50 bags
```

After review and confirmation:

1. canonical project records exist
2. source provenance exists
3. OG can answer project-specific queries
4. dependencies drive blocker reasoning
5. requirements drive material reasoning

Then submit:

> Ground-floor blockwork is finished. The electrician didn't come today. We only have ten bags of cement left and plastering starts tomorrow.

OG must derive:

```text
Ground-floor blockwork
→ completed

Electrical rough-in
→ blocked

Ground-floor plastering
→ at risk

Cement
→ 10 on hand

Required
→ 100

Shortage
→ 90

Material request
→ 90

Approval
→ pending
```

Change the project's requirement to:

```text
80 bags
```

The same operational scenario must produce:

```text
70-bag shortage
```

That is the proof that OG operates on **project truth rather than model assumptions**.

---

# Definition of Done

Do not declare Project Initialization complete until:

* [ ] Canonical import contracts exist.
* [ ] Source provenance exists.
* [ ] Import lifecycle is durable.
* [ ] One production source adapter exists.
* [ ] Gemini extraction calls Google Gen AI / Vertex directly with no ADK session.
* [ ] Extraction uses structured output.
* [ ] Gemini cannot create canonical IDs.
* [ ] Deterministic validation exists.
* [ ] Dependency cycles are rejected.
* [ ] Units are normalized and validated.
* [ ] Requirements link task ↔ material.
* [ ] Review occurs before mutation.
* [ ] Import confirmation is server-authoritative.
* [ ] Import is idempotent.
* [ ] Canonical records persist.
* [ ] Initial actual state is supported.
* [ ] OG project queries use imported data.
* [ ] OG dependency reasoning uses imported dependencies.
* [ ] OG material reasoning uses imported requirements.
* [ ] Requirement changes change operational results.
* [ ] Import failures do not corrupt canonical state.
* [ ] Import ActivityEvents exist.
* [ ] Import traces exist.
* [ ] Cross-project access is prevented.
* [ ] Golden Scenario remains PASS.
* [ ] Conversational Operations remain PASS.
* [ ] Adding a future source adapter does not require redesigning the canonical project model.

---

# Engineering Standard

Do not optimize this system around a demo script.

Do not build every possible construction integration either.

Build the **first production-complete ingestion vertical**:

```text
SOURCE
→ EXTRACT
→ VALIDATE
→ REVIEW
→ COMMIT
→ OPERATE
```

Then every future source plugs into the same pipeline.

That is the foundation OG Foreman needs to become a real construction SaaS.
