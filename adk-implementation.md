# P0 ARCHITECTURE CORRECTION — REPLACE CUSTOM ORCHESTRATION WITH NATIVE GOOGLE ADK 2.0

## Objective

OG Foreman is a Google ADK application.

The current orchestration architecture violates ADR-001 because significant workflow-runtime responsibilities were reimplemented manually instead of using Google ADK 2.0's native Workflow Runtime.

Correct this now.

This is not a cosmetic refactor.

The target is:

**Google ADK owns agent workflow execution, graph state, pause/resume, node execution, retries, and session continuity.**

OG application code owns:

* construction domain rules
* authentication / authorization
* canonical project IDs
* typed tools
* Firestore project state
* ActivityEvents / user-facing audit projections
* safety / approval policy
* domain idempotency

Do not maintain two competing orchestration engines.

---

# CURRENT ARCHITECTURAL VIOLATIONS

Audit and confirm each before changing code.

## 1. Custom RuntimeManager

Current:

`app/workflows/runtime.py`

contains a custom `RuntimeManager` responsible for concepts such as:

* durable agent runs
* workflow steps
* checkpointing
* paused state
* continuation
* retry/resume semantics

This duplicates responsibilities belonging to ADK 2.0 Workflow Runtime.

ADR-001 requires Google ADK primitives.

The custom runtime must cease being the orchestration source of truth.

---

## 2. InMemorySessionService in Real Execution

Current ADK Runner uses:

`InMemorySessionService()`

This means ADK session/event state disappears with process lifecycle and OG compensates by manually rebuilding workflow durability elsewhere.

This defeats the purpose of using the ADK execution/session model.

Production and staging must not depend on `InMemorySessionService`.

Local unit tests may use it when explicitly appropriate.

---

## 3. Fake ADK Bridge

Current `SiteUpdateWorkflowAgent` appears to:

1. enter ADK Runner
2. call one procedural Python workflow
3. execute most orchestration outside native ADK graph/tool execution
4. emit one generic completion event

This makes ADK a wrapper around custom application orchestration rather than the actual agent runtime.

This must be removed.

ADK must execute the real nodes/tools that form the Golden Scenario.

---

# TARGET ARCHITECTURE

Implement the Golden Scenario as a real ADK 2.0 Workflow.

Conceptual graph:

```text
START
  │
  ▼
load_site_update
  │
  ▼
prepare_multimodal_input
  │
  ▼
interpret_site_update
  │
  ▼
retrieve_project_context
  │
  ▼
resolve_canonical_entities
  │
  ▼
route_facts
  │
  ├───────────────┬────────────────┐
  ▼               ▼                ▼
progress_node   blocker_node    material_node
  │               │                │
  │               ▼                ▼
  │          dependency_impact   shortage_analysis
  │               │                │
  └───────────────┴────────────────┘
                  │
                  ▼
              merge_actions
                  │
                  ▼
             validate_policy
                  │
          ┌───────┴────────┐
          │                │
     AUTO EXECUTE      APPROVAL REQUIRED
          │                │
          ▼                ▼
     execute_tools      HITL / PAUSE
          │                │
          │          approval event
          │                │
          │              RESUME
          └───────┬────────┘
                  ▼
          update_daily_log
                  │
                  ▼
          emit_activity/audit
                  │
                  ▼
                 END
```

This graph is the Golden Scenario.

Do not represent it as one Python function hidden inside one ADK node.

---

# PHASE 0 — INSPECT ACTUAL ADK VERSION

Before modifying architecture:

1. Inspect:

   * `pyproject.toml`
   * lockfile
   * installed `google-adk`
   * `agents-cli-manifest.yaml`
   * current ADK imports

2. Confirm exact installed ADK 2.x version.

3. Inspect the ADK 2.0 Workflow APIs available in that exact version.

4. Prefer current public APIs and official samples.

Do not write against remembered 1.x APIs.

Do not downgrade ADK to make existing custom code easier to preserve.

Document findings in:

`docs/ADK_NATIVE_MIGRATION.md`

---

# PHASE 1 — SEPARATE DOMAIN STATE FROM AGENT RUNTIME STATE

Lock this boundary.

## Firestore remains authoritative for construction domain data

Examples:

* Projects
* Tasks
* Issues
* Materials
* MaterialRequests
* Approvals
* DailyLogs
* Attachments
* ActivityEvents
* business-facing AgentRun projections if still useful

Firestore does NOT become a second custom ADK workflow engine.

## ADK owns agent execution state

Examples:

* session
* workflow node state
* invocation/event history
* workflow continuation state
* native workflow outputs
* pause/resume execution context

Do not duplicate ADK workflow checkpoints into a custom state machine.

---

# PHASE 2 — REPLACE IN-MEMORY PRODUCTION SESSIONS

Remove `InMemorySessionService()` from staging/production execution.

Use a supported durable ADK session backend.

Preferred target for OG's Google Cloud deployment:

**Agent Platform Sessions**

If current deployment/runtime configuration makes that unavailable, inspect the supported Google-managed durable session alternatives for the exact installed tooling and document the decision.

Do NOT:

* invent `FirestoreSessionService`
* manually serialize Runner internals
* add another custom session database
* silently fall back to in-memory in staging/production

Configuration should make the choice explicit.

Example conceptual configuration:

```text
local unit tests:
    in_memory

local integration:
    configurable durable/fake boundary

staging:
    agent_platform_sessions

production:
    agent_platform_sessions
```

Fail startup in staging/production if configured with an in-memory session backend.

---

# PHASE 3 — CREATE REAL ADK WORKFLOW NODES

Replace the procedural Golden Scenario function with actual ADK workflow nodes.

At minimum create explicit execution nodes for:

```text
receive/input preparation
multimodal interpretation
project context retrieval
canonical entity resolution
progress processing
blocker processing
dependency impact
material processing
action composition
policy evaluation
approval/HITL
tool execution
daily log projection
completion
```

Use the ADK 2.0 Workflow graph API for routing.

Use native routing/edges rather than:

```python
if ...
elif ...
while ...
custom_checkpoint(...)
runtime_manager.pause(...)
runtime_manager.resume(...)
```

when the logic represents workflow orchestration.

Normal deterministic domain code inside a node is fine.

The distinction:

```text
Workflow routing        → ADK
Business/domain logic   → OG code
Database mutation       → typed OG tools/services
```

---

# PHASE 4 — REAL ADK TOOL EXECUTION

Convert the current fake bridge into actual tool/node execution.

Critical typed tools remain:

```text
get_project_context
resolve_task
complete_task
create_task

resolve_material
create_material
update_material_quantity
create_material_request

resolve_issue
create_issue
resolve_issue

calculate_schedule_impact

create_approval
resolve_approval

update_daily_log

record_activity
```

Do not allow Gemini to write directly to Firestore.

ADK invokes controlled tools.

Tools invoke existing domain services.

Domain services enforce:

* authorization
* canonical IDs
* optimistic concurrency
* state transitions
* idempotency
* ActivityEvents

---

# PHASE 5 — GEMINI BOUNDARY

Preserve the architecture we already established:

```text
Gemini
   ↓
extract / interpret / reason
   ↓
structured facts or proposed action
   ↓
deterministic entity resolution
   ↓
canonical IDs
   ↓
policy validation
   ↓
typed tool
   ↓
Firestore
```

Gemini must never own:

* canonical database IDs
* authorization
* version tokens
* mutation/idempotency tokens
* approval authority
* Firestore writes

Use schema-constrained structured output wherever supported.

---

# PHASE 6 — NATIVE PARALLELISM / FAN-OUT

The mixed site update:

```text
"Blockwork is complete.
Electrician didn't come.
We have 10 bags of cement."
```

contains multiple independent facts.

Represent this using ADK workflow fan-out/fan-in where appropriate.

Conceptually:

```text
interpret
    │
    ├──── progress
    │
    ├──── blocker
    │
    └──── materials
             │
          fan-in
             │
      evaluate combined impact
```

Do not use custom thread/task orchestration to reproduce ADK graph execution.

Each branch should return typed outputs.

---

# PHASE 7 — NATIVE HITL PAUSE / RESUME

This is critical.

Current custom RuntimeManager pause/resume behavior must no longer control the Golden workflow.

Material approval flow should become a native ADK human-in-the-loop / interruption boundary.

Required behavior:

```text
material shortage
      ↓
create MaterialRequest
      ↓
create Approval
      ↓
ADK workflow reaches approval boundary
      ↓
workflow execution pauses
      ↓
session/workflow state remains durable
      ↓
user approves
      ↓
continuation event/input enters
      ↓
same logical ADK workflow resumes
      ↓
approved external/domain action executes once
      ↓
workflow completes
```

Rejection:

```text
PAUSED
  ↓
REJECT
  ↓
safe rejection branch
  ↓
no consequential action
  ↓
workflow terminates correctly
```

No second shadow workflow.

No manually reconstructed continuation graph.

---

# PHASE 8 — AgentRun BECOMES A PROJECTION, NOT THE ENGINE

OG currently needs `AgentRun` for:

* product Activity
* operations UI
* audit
* debugging
* trace correlation

Keep it if useful.

But redefine its role.

It is a **projection of ADK execution**, not the state machine controlling ADK.

Example:

```text
ADK session/workflow
        ↓
events / callbacks / node transitions
        ↓
OG AgentRun projection
```

AgentRun may record:

```text
run_id
ADK session ID
ADK invocation/workflow ID
project_id
trigger
status
current user-facing stage
started_at
completed_at
trace_id
error summary
```

Do not use AgentRun.step to decide which Python function to manually execute next.

---

# PHASE 9 — ACTIVITY REMAINS PRODUCT AUDIT

Do not delete ActivityEvents.

Activity is a user-facing construction audit trail.

ADK event history is not a replacement for:

```text
task.completed
issue.created
material.quantity_updated
material.requested
approval.requested
approval.approved
daily_log.updated
```

Architecture:

```text
ADK execution event
       │
       ├──── observability / traces
       │
       └──── domain tool executes
                  │
                  ▼
             ActivityEvent
```

Keep the two concepts separate.

---

# PHASE 10 — CONVERSATIONAL OG USES THE SAME ADK CORE

Do not build a second runtime for chat.

Conversational input routes into ADK.

Conceptually:

```text
universal OG composer
        ↓
ADK conversation/session
        ↓
intent decision
   ┌────┼─────────┐
   │    │         │
 query advice   operation/site update
   │    │         │
   │    │         └── native ADK workflow/tool path
   │    │
   └────┴── project-context tools
```

The existing Golden Scenario workflow should remain reusable when conversation is classified as a site update.

Do not recreate site-update semantics inside conversational Python handlers.

---

# PHASE 11 — REMOVE CUSTOM RUNTIME

Only after native ADK paths pass tests:

Remove or deprecate:

`app/workflows/runtime.py`

and all custom mechanisms whose only purpose was to reproduce ADK runtime functionality, including as applicable:

* custom checkpoint store
* custom next-step execution
* custom pause markers
* custom resume routing
* custom retry scheduler
* custom workflow cursor
* custom graph state machine

Do not delete domain idempotency or business audit logic.

Before deleting each component, prove that ADK now owns the equivalent runtime responsibility.

---

# PHASE 12 — REMOVE FAKE SITEUPDATEWORKFLOWAGENT

Replace the current bridge that effectively does:

```text
ADK Runner
   ↓
one Python workflow call
   ↓
generic done event
```

with:

```text
ADK Runner
   ↓
actual Workflow
   ↓
multiple named nodes
   ↓
native node/tool events
   ↓
actual workflow output
```

A tracing session should visibly show meaningful nodes.

Examples:

```text
interpret_site_update
resolve_project_context
process_progress
process_blocker
process_material
approval_gate
update_daily_log
```

Not one opaque:

```text
site_update_workflow
```

span that hides all execution.

---

# PHASE 13 — ADK EVENT / SESSION COMPATIBILITY

ADK 2.0 events include workflow/node execution metadata.

Ensure any API, persistence adapter, event projection, trace parser, or strict JSON validator accepts current ADK 2.0 Event fields.

Do not discard native workflow fields merely because the old application schema did not expect them.

Persist/expose enough identifiers to correlate:

```text
ADK session
ADK invocation
workflow
node
OG AgentRun
project
trace
```

---

# PHASE 14 — RESTART DURABILITY TEST

This is the architecture acceptance test.

Execute Golden Scenario until:

```text
WAITING FOR MATERIAL APPROVAL
```

Then intentionally terminate/restart the application process/container.

After restart:

1. ADK durable session exists.
2. Native workflow state exists.
3. Approval remains PENDING.
4. Project state remains correct in Firestore.
5. Approve the request.
6. Same logical ADK workflow resumes.
7. External/domain action executes once.
8. Workflow completes.
9. AgentRun projection updates.
10. Activity records completion.

If custom RuntimeManager state is required to recover the workflow, migration has failed.

---

# PHASE 15 — DUPLICATE / RETRY DURABILITY

Test:

```text
same site event delivered twice
```

Expected:

* ADK/runtime may receive retries
* OG domain idempotency prevents duplicate mutation
* only one material request
* only one task completion
* only one consequential external action

ADK handles workflow execution/retry.

Domain layer handles business idempotency.

Do not confuse these responsibilities.

---

# PHASE 16 — LIVE MULTIMODAL TEST

Run the real Golden Scenario:

```text
voice
+
photo
```

Voice:

"OG, ground-floor blockwork is finished.
The electrician didn't come today.
We only have about ten bags of cement left
and plastering starts tomorrow."

````

Required path must visibly be:

```text
ADK workflow started
→ multimodal Gemini node
→ project context node
→ entity resolution
→ parallel fact handling
→ blocker dependency impact
→ material shortage
→ typed mutations
→ approval/HITL
→ pause
→ approve
→ ADK resume
→ action
→ Daily Log
→ completion
````

No custom runtime may secretly drive the transitions.

---

# PHASE 17 — CONVERSATIONAL REGRESSION

After migration verify:

```text
"what's up?"
→ ADK conversation + project tools

"how about site clearance?"
→ project entity query

"we have 50 bags of cement now"
→ typed material mutation

"add 60 pieces of building wire"
→ clarification

"yes on site"
→ clarification continuation

"move plastering to Friday"
→ proposal/confirmation path

"buy 50 bags cement"
→ approval path
```

Conversational memory must use durable ADK session/context appropriately while project truth remains Firestore-backed domain state.

---

# PHASE 18 — OBSERVABILITY PROOF

Capture Cloud Trace / ADK events from a complete run.

We must be able to prove to judges:

```text
OG is not using ADK as a label.

OG is executing through ADK's actual workflow runtime.
```

Evidence should show:

* workflow name
* node transitions
* Gemini invocation
* tool execution
* parallel branches where used
* HITL interruption
* resume
* workflow output
* trace correlation

Do not expose private chain-of-thought.

Show observable execution only.

---

# PHASE 19 — DOCUMENT ADR COMPLIANCE

Update ADR-001 to record:

```text
Google ADK 2.0 Workflow Runtime
is OG Foreman's sole agent orchestration runtime.
```

Document responsibility boundaries:

```text
ADK
→ workflow execution
→ session/runtime state
→ node routing
→ HITL interruption/resume
→ retry/runtime behavior
→ workflow observability

Firestore
→ construction project truth

OG domain services
→ authorization
→ business state transitions
→ canonical identity
→ business idempotency
→ typed mutations

Activity / AgentRun
→ user-facing/audit projections
```

Explicitly prohibit future custom orchestration runtimes unless an ADR supersedes ADR-001 with documented evidence that ADK cannot satisfy the requirement.

---

# REQUIRED MIGRATION TESTS

All must pass:

```text
Golden Scenario
PASS

Golden Scenario restart during approval
PASS

Voice multimodal
PASS

Photo multimodal
PASS

Parallel mixed fact routing
PASS

Material approval pause/resume
PASS

Material rejection
PASS

Duplicate event
PASS

Duplicate approval
PASS

Stale approval
PASS

Conversational query
PASS

Conversational mutation
PASS

Conversational clarification continuation
PASS

Daily Log projection
PASS

Activity audit
PASS

Staging deployment
PASS

Live Gemini evaluation
PASS
```

---

# HARD ACCEPTANCE CRITERIA

Do not declare migration complete unless:

* [ ] `RuntimeManager` no longer controls agent workflow progression.
* [ ] Staging/production does not use `InMemorySessionService`.
* [ ] No custom Firestore ADK runtime/session implementation was invented unnecessarily.
* [ ] A supported durable ADK session backend is configured.
* [ ] Golden Scenario is represented by a real ADK 2.0 workflow graph.
* [ ] Workflow contains multiple meaningful native nodes.
* [ ] Gemini execution occurs inside native ADK execution.
* [ ] Typed OG tools are dispatched through the ADK execution path.
* [ ] Fan-out/fan-in uses native ADK workflow primitives where appropriate.
* [ ] Approval uses native ADK HITL/interruption semantics.
* [ ] Restart while paused resumes the same logical workflow.
* [ ] AgentRun is a projection, not workflow authority.
* [ ] Firestore remains construction-domain truth.
* [ ] ActivityEvent remains business audit truth.
* [ ] Duplicate business mutations remain prevented.
* [ ] Conversational OG uses the same ADK runtime.
* [ ] Cloud Trace proves native ADK workflow execution.
* [ ] ADR-001 reflects the implemented architecture.
* [ ] All previous Golden Scenario behavior remains passing.

---

# DO NOT DO

Do not:

* patch RuntimeManager and call migration complete
* keep both custom runtime and ADK runtime active
* create a Firestore clone of ADK session internals without necessity
* wrap the old Python pipeline inside one Workflow node
* emit one generic event and claim native ADK
* move domain truth into ADK session state
* allow Gemini to own canonical project IDs
* allow Gemini to write Firestore
* remove domain authorization
* remove business idempotency
* remove ActivityEvents
* redesign the frontend during this migration
* add X Layer/Vana/new product features
* weaken the Golden Scenario to simplify migration

---

# FINAL TARGET

The architecture after migration must be:

```text
                       USER / EVENT
                            │
                            ▼
                    GOOGLE ADK RUNNER
                            │
                            ▼
                    ADK 2.0 WORKFLOW
                            │
       ┌────────────────────┼────────────────────┐
       ▼                    ▼                    ▼
    GEMINI                TOOLS              HITL
 reasoning          deterministic actions   approval
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                            ▼
                    OG DOMAIN SERVICES
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
           FIRESTORE                 ACTIVITY
        project truth              audit/projection
```

**Google ADK is the agent runtime.**

**OG Foreman is the construction intelligence and domain.**

**Firestore is project truth.**

There must be no second home-grown agent runtime between them.
