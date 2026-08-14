# OG Foreman — Conversational Operations Implementation Plan

## Status

**Golden Scenario:** PASS AND LOCKED

**Active phase:** Phase 11 — Advice Mode

The existing Golden Scenario is the foundation of OG Foreman and must not regress:

**voice/photo site update → OG understands it → updates project state → detects blocker/material risk → creates actions → pauses for approval → resumes → logs everything**

This document defines the next implementation phase:

> **Turn OG into the natural-language interface to the construction project without rebuilding the proven operational engine.**

---

# 1. Product Goal

OG should support both conversation and action.

A user should be able to speak naturally:

```text
"what's up?"
"what happened today?"
"what's blocking us?"
"how much cement do we have?"
"we have 35 bags now"
"mark plumbing complete"
"Kofi is handling electrical"
"electrical is sorted"
"create a scaffolding task for tomorrow"
"wdyt about plastering tomorrow?"
"move plastering to Friday"
"we need another 90 bags of cement"
```

OG must understand which messages are:

* conversation
* project questions
* project advice
* direct project mutations
* full site updates
* clarifications
* consequential actions requiring approval

---

# 2. Core Architecture

```text
                         USER MESSAGE
                              │
                              ▼
                     Conversational OG
                              │
                        Intent Router
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
        CASUAL          PROJECT QUERY       PROJECT ACTION
          │                   │                   │
          ▼                   ▼                   ▼
      Respond           Retrieve State      Resolve Entity
                                                  │
                                                  ▼
                                          Validate Mutation
                                                  │
                                  ┌───────────────┼───────────────┐
                                  │               │               │
                                SAFE          CONFIRM          APPROVAL
                                  │               │               │
                                  ▼               ▼               ▼
                            Existing Tool     User confirms   Existing
                                  │               │          Approval Flow
                                  └───────────────┼───────────────┘
                                                  ▼
                                          Persist Project State
                                                  │
                                                  ▼
                                           Activity Event
                                                  │
                                                  ▼
                                            OG Response
```

## Non-negotiable architecture rule

Conversational OG must never directly mutate the database.

Every state change must pass through the same domain services and typed tools already used by the Golden Scenario.

Examples:

```text
Task service/tool
Material service/tool
Issue service/tool
Schedule service/tool
Approval service/tool
Report service/tool
Project service/tool
```

Never:

```text
LLM
↓
raw Firestore/database mutation
```

The language model reasons.

The domain layer validates.

Typed tools perform actions.

The database remains the source of truth.

---

# 3. Golden Core Protection

Before implementing conversational operations, document and protect the Golden Scenario.

Create:

```text
docs/
├── GOLDEN_SCENARIO.md
├── CONVERSATIONAL_OPERATIONS.md
└── IMPLEMENTATION_STATUS.md
```

`GOLDEN_SCENARIO.md` must document:

```text
voice/photo
→ multimodal interpretation
→ project context retrieval
→ project mutations
→ blocker/material reasoning
→ follow-up actions
→ approval
→ durable pause
→ resume
→ activity/audit
```

## Regression rule

Before each conversational phase:

```text
Golden Scenario regression tests → PASS
```

After each phase:

```text
Golden Scenario regression tests → STILL PASS
```

If a conversational change breaks the Golden Scenario, stop and fix the regression before proceeding.

---

# PHASE 0 — Implementation Audit

## Goal

Understand the existing messaging, agent, tool, and project-context architecture before adding another orchestration layer.

Do not change product behavior yet.

## Inspect

Identify:

* existing site-update intake entry points
* Gemini interpreter
* ADK coordinator
* existing tools
* project repositories
* context retrieval services
* agent-run persistence
* approval workflow
* activity logging
* current OG composer/chat UI
* current session/conversation state
* authentication/project scoping

## Create

Update:

```text
docs/CONVERSATIONAL_OPERATIONS.md
docs/IMPLEMENTATION_STATUS.md
```

Document:

* existing components to reuse
* components requiring extension
* new components required
* exact route from conversational OG into Golden workflow
* risks of duplicate orchestration

## Acceptance Gate

No new user-visible functionality.

Golden Scenario still passes.

Architecture for Phase 1 is clearly documented.

---

# PHASE 1 — Intent Router

## Goal

Classify incoming conversational messages before deciding whether to answer, retrieve, advise, or act.

Create a typed intent model.

Recommended taxonomy:

```text
CASUAL
PROJECT_QUERY
PROJECT_ADVICE
PROJECT_MUTATION
SITE_UPDATE
CLARIFICATION_RESPONSE
CONFIRMATION_RESPONSE
UNKNOWN
```

Recommended output schema:

```text
IntentDecision

intent
confidence
requested_action
referenced_entities
requires_project_context
requires_mutation
ambiguity
reason_code
```

Do not include private chain-of-thought.

`reason_code` should be a short observable classification reason if useful for debugging.

## Examples

```text
"yo OG"
→ CASUAL

"what's up?"
→ PROJECT_QUERY when a project is active

"what happened today?"
→ PROJECT_QUERY

"wdyt about tomorrow?"
→ PROJECT_ADVICE

"we have 35 bags of cement"
→ PROJECT_MUTATION

"mark plumbing complete"
→ PROJECT_MUTATION

"blockwork is done, electrician didn't show and cement is low"
→ SITE_UPDATE

"yes, ground-floor plastering"
→ CLARIFICATION_RESPONSE

"confirm"
→ CONFIRMATION_RESPONSE when a pending confirmation exists
```

## Rules

* Do not mutate from low-confidence intent.
* `SITE_UPDATE` routes into the existing Golden workflow.
* Do not duplicate Golden Scenario interpretation logic inside the router.
* The router decides **where the message goes**, not what project changes occur.

## Tests

Build eval cases covering:

* greetings
* project questions
* advice
* explicit mutation
* full site updates
* ambiguous instructions
* confirmations
* clarification answers

## Acceptance Gate

Intent routing is typed and tested.

Golden site-update text still enters the existing operational workflow.

Golden Scenario remains green.

---

# PHASE 2 — Project Context Service

## Goal

Allow OG to answer questions using current persisted project state.

Create a structured project-context retrieval service.

Do not dump the entire project database into the model.

Retrieve only relevant information according to the user query.

Supported context domains:

```text
Project
Tasks
Issues
Materials
Material Requests
Approvals
Schedule
Daily Logs
Recent Activity
Project Members
```

## Example

User:

```text
"what's up?"
```

Potential retrieved context:

```text
2 completed tasks today
1 blocked task
1 material risk
1 pending approval
tomorrow's scheduled work
```

OG:

```text
"Site's moving. Blockwork is done, but electrical is still blocked and the cement request needs your approval. Tomorrow's plastering is the main thing at risk."
```

## Requirements

* project scoped
* permission aware
* deterministic retrieval
* efficient
* typed output
* database is source of truth
* conversation memory cannot override persisted state

## Acceptance Gate

OG accurately answers:

```text
what's up?
what happened today?
what's blocking us?
what's late?
what materials are low?
what needs approval?
what happens tomorrow?
who owns electrical?
why is plastering at risk?
```

No project mutations occur during queries.

Golden Scenario remains green.

---

# PHASE 3 — Conversational Response Layer

## Goal

Make OG feel like a natural project coordinator rather than a query engine.

Responses should be concise, contextual, and operational.

## Tone

Prefer:

```text
"Electrical is still blocked."
"Cement is down to 10 bags."
"You have one request waiting for approval."
"Blockwork is done."
```

Avoid:

```text
"Based on my analysis of current project data..."
"I have successfully processed your request..."
"The AI system has determined..."
```

## Casual + contextual behavior

User:

```text
"yo"
```

OG:

```text
"What's up?"
```

User:

```text
"what's up?"
```

OG should preferably answer from the project:

```text
"Blockwork is done. Electrical is still blocked, and the cement request needs you."
```

## Important distinction

Casual conversation can be casual.

Project conversation should be grounded.

OG should not invent project facts to sound conversational.

## Acceptance Gate

OG can hold a short natural conversation while remaining grounded in live project state.

---

# PHASE 4 — Entity Resolution

## Goal

Before performing project mutations, OG must identify exactly which project object the user means.

Supported entities:

```text
Task
Issue
Material
Material Request
Schedule Activity
Project Member
Daily Log
```

Resolution strategy:

```text
exact ID/name
→ project-local alias
→ normalized name
→ contextual match
→ fuzzy match with confidence threshold
→ clarification
```

## Examples

User:

```text
"mark plumbing complete"
```

If only one plumbing task exists:

```text
Ground-floor plumbing
tsk_123
```

If two exist:

```text
Ground-floor plumbing
First-floor plumbing
```

OG must ask:

```text
"Which one — ground-floor or first-floor plumbing?"
```

No mutation occurs until resolved.

## Material example

```text
"cement is 35 now"
```

Resolve:

```text
Cement
mat_123
```

Do not create a duplicate material record.

## Acceptance Gate

Ambiguous entity references never trigger project mutations.

Entity resolution is project scoped and tested.

Golden Scenario remains green.

---

# PHASE 5 — Safe Task Operations

## Goal

Allow natural-language task management through existing Task tools.

Support initially:

```text
create task
complete task
change status
assign task
reassign task
change priority
add note
```

## Examples

```text
"create a task for scaffolding tomorrow"
```

→ `TaskTool.create_task(...)`

```text
"mark plumbing complete"
```

→ entity resolution
→ domain validation
→ `TaskTool.complete_task(...)`

```text
"Kofi is handling electrical now"
```

→ resolve task
→ resolve project member
→ `TaskTool.assign_task(...)`

## Response

```text
"Done. Ground-floor plumbing is marked complete."
```

Every mutation must produce:

```text
domain mutation
ActivityEvent
OG confirmation
```

## Acceptance Gate

Task changes persist after refresh/sign-in.

No direct DB writes.

No duplicate mutations on repeated commands.

---

# PHASE 6 — Safe Material Operations

## Goal

Make Materials controllable through normal conversation.

Support:

```text
create material
update on-site quantity
update required quantity
record delivery
add material note
```

## Examples

```text
"we have 35 bags of cement now"
```

→ resolve Cement
→ update quantity
→ activity event

OG:

```text
"Done. Cement is now recorded at 35 bags."
```

```text
"the cement delivery came"
```

→ resolve relevant request/delivery
→ update state where sufficiently clear

If ambiguous:

```text
"Did all 90 bags arrive, or only part of the delivery?"
```

## Important

Statements that imply shortage/risk may route into existing material reasoning.

Example:

```text
"we're down to 10 bags and plastering starts tomorrow"
```

Should preferably route through the existing site/material-risk workflow instead of only performing a raw quantity update.

## Acceptance Gate

Material state changes persist and produce activity.

Material-risk semantics are not duplicated.

Golden Scenario remains green.

---

# PHASE 7 — Safe Issue Operations

## Goal

Allow conversational management of blockers and issues.

Support:

```text
create issue
assign issue
change status
resolve issue
add note
```

Example:

```text
"electrical is sorted"
```

OG:

1. resolves active electrical issue
2. validates meaning
3. resolves issue
4. updates related state where existing domain logic supports it
5. logs activity

Response:

```text
"Got it. I've resolved the electrical blocker."
```

If multiple electrical issues exist:

```text
"Which electrical issue do you mean?"
```

## Acceptance Gate

Issue resolution does not bypass dependency/schedule logic.

Golden Scenario remains green.

---

# PHASE 8 — Mutation Policy Engine

## Goal

Separate routine actions from consequential project decisions.

Every supported mutation receives one of four policy classes:

```text
AUTO_EXECUTE
CONFIRM_FIRST
APPROVAL_REQUIRED
DENY_OR_ESCALATE
```

## AUTO_EXECUTE

Examples:

```text
reported material quantity
normal task creation
explicit task completion
routine assignment
add note
normal issue resolution
```

## CONFIRM_FIRST

Examples:

```text
changing planned dates
changing dependencies
bulk task updates
reopening completed work
cancelling tasks
deleting records
high-impact status changes
```

Example:

User:

```text
"move plastering to Friday"
```

OG:

```text
"Moving plastering to Friday will also affect painting preparation. Want me to update the schedule?"
```

Actions:

```text
Cancel
Update schedule
```

## APPROVAL_REQUIRED

Use existing approval infrastructure for:

```text
material purchase
financial commitment
external commitment
major schedule action if policy requires it
```

Do not create a conversational-only approval system.

## DENY_OR_ESCALATE

Examples:

```text
professional structural certification
unsafe automated engineering judgment
actions outside user permissions
```

## Acceptance Gate

No mutation depends solely on arbitrary LLM judgment about whether it is safe.

Policy is explicit and testable.

---

# PHASE 9 — Schedule Operations

## Goal

Allow OG to reason about and modify project scheduling safely.

Support:

```text
query schedule
move task/activity
change planned dates
inspect dependency impact
propose schedule change
```

Example:

```text
"move plastering to Friday"
```

Flow:

```text
resolve plastering activity
→ retrieve dependencies
→ calculate impact
→ policy classification
→ confirmation
→ ScheduleTool
→ persist
→ ActivityEvent
```

Response example:

```text
"That shifts plastering to Friday and moves painting preparation by one day.

Update the schedule?"
```

## Acceptance Gate

Schedule changes always consider dependency impact where project data supports it.

No silent high-impact rescheduling.

---

# PHASE 10 — Unified Site Update Routing

## Goal

Text/chat site updates should converge with voice/photo updates on the existing Golden Scenario engine.

Examples:

```text
"blockwork is done, electrician didn't show and cement is low"
```

→ `SITE_UPDATE`

→ existing site-update workflow

Not:

```text
chat-specific task mutation
+
chat-specific issue creation
+
chat-specific material mutation
```

The Golden workflow already knows how to do this.

Entry channels should converge:

```text
Voice ─────┐
Photo ─────┤
Text ──────┼──→ Golden Site Update Workflow
Chat ──────┘
```

## Acceptance Gate

Equivalent site facts produce equivalent persisted state regardless of input channel.

---

# PHASE 11 — Advice Mode

## Goal

Allow OG to reason about the project without automatically changing it.

Example:

```text
"wdyt about plastering tomorrow?"
```

OG retrieves:

```text
schedule
cement quantity
material requirements
electrical blocker
dependencies
open issues
```

Then provides a recommendation:

```text
"I'd hold off committing to tomorrow yet. Cement is still below the requirement and electrical remains blocked."
```

Advice does not mutate state.

If user replies:

```text
"move it to Friday then"
```

That is a new `PROJECT_MUTATION`.

## Acceptance Gate

Recommendation and execution remain separate concepts.

---

# PHASE 12 — Conversational Memory

## Goal

Support natural multi-turn references without making memory the source of project truth.

Memory may retain:

```text
recent referenced entities
recent topic
pending clarification
pending confirmation
pending approval context
recent proposed action
```

Example:

```text
User:
"what's blocking plastering?"

OG:
"Electrical rough-in is still blocking it."

User:
"who owns it?"

OG:
"Kofi."

User:
"assign it to Ama instead."

OG:
"Done. Electrical rough-in is now assigned to Ama."
```

The task itself must always be revalidated against current persisted state before mutation.

## Acceptance Gate

Pronouns and follow-ups work reliably.

Stale memory never overwrites newer project truth.

---

# PHASE 13 — OG Drawer Integration

## Goal

Expose conversational operations through the global OG interface.

Desktop:

```text
right-side drawer
```

Mobile:

```text
full-screen sheet
```

Persistent action:

```text
✦ Ask OG
```

Composer:

```text
text
voice
photo
attachment
```

## Response structure

Avoid long chat essays.

Example:

```text
OG

Electrical is still blocked.
Cement is now at 35 bags.

DONE
✓ Updated cement quantity

NEEDS YOU
Material request MR-014

[Review]
```

For mutations requiring confirmation:

```text
PROPOSED CHANGE

Plastering
Thursday → Friday

Impact
Painting preparation moves by 1 day.

[Cancel] [Update schedule]
```

## Acceptance Gate

OG feels embedded in the PM interface rather than being a separate chatbot product.

---

# PHASE 14 — Conversational Activity & Audit

## Goal

All project-significant conversational actions should be auditable.

Log:

```text
mutation requested
entity resolved
confirmation requested
confirmation accepted
domain mutation performed
approval requested
approval resolved
workflow resumed
```

Do not log meaningless casual messages into project Activity.

Example:

```text
15:32  ✓ Task completed
          Ground-floor plumbing
          Requested through OG by Ace

15:31  ✦ OG action requested
          "Mark plumbing complete"
```

## Important

Do not expose private chain-of-thought.

Audit observable system actions, state transitions, objects, IDs, timestamps, and user-visible reasons only.

## Acceptance Gate

A manager can identify:

```text
who requested change
what OG changed
which record changed
when it happened
whether approval occurred
```

---

# PHASE 15 — Conflict, Concurrency & Idempotency

## Goal

Conversational control must be as reliable as existing UI/API CRUD.

Test:

### Duplicate command

```text
"mark plumbing complete"
```

sent twice.

Expected:

```text
one actual completion
no duplicate side effects
```

### Stale mutation

Two users update same record.

Expected:

```text
latest valid state preserved
conflict surfaced
no silent overwrite
```

### Conflicting quantity

Persisted value changed after conversational context was loaded.

Expected:

```text
optimistic concurrency check
fresh state reload
safe response
```

### Ambiguous deletion

```text
"delete that task"
```

Expected:

* resolve exact task
* confirm destructive action
* verify permission
* execute only once

## Acceptance Gate

Conversational CRUD passes the same concurrency and idempotency expectations as direct API/UI operations.

---

# PHASE 16 — Conversational Evals

## Goal

Establish a reproducible quality benchmark.

Eval categories:

```text
casual
project query
project advice
task mutation
material mutation
issue mutation
schedule mutation
site update
clarification
confirmation
ambiguous entity
ambiguous intent
approval action
duplicate command
stale state
multi-turn reference
permissions
```

Golden examples:

```text
"what's up?"
→ grounded project summary

"we have 35 bags of cement now"
→ material mutation

"mark plumbing done"
→ task mutation

"electrical is sorted"
→ issue resolution

"move plastering to Friday"
→ impact evaluation + confirmation

"buy 100 bags of cement"
→ approval workflow

"plastering is basically done"
→ clarification, not completion

"what's blocking us?"
→ query only

"we need 10 more bags and the electrician didn't show"
→ site-update workflow
```

## Acceptance Gate

Evaluation suite is deterministic enough to compare releases.

Golden Scenario remains fully green.

---

# PHASE 17 — Final Conversational Golden Flow

The feature is not considered complete until this flow works end to end.

```text
USER
yo OG, what's up?

OG
Site's moving. Blockwork is done. Electrical is
still blocked, and the cement request needs you.

USER
how much cement do we have?

OG
10 bags are currently recorded.

USER
delivery came. we've got 100 now.

OG
Done. Cement is now recorded at 100 bags.

USER
electrical is sorted too.

OG
Got it. I've resolved the electrical blocker.

USER
wdyt about plastering tomorrow?

OG
Looks better now. Cement is sufficient and the
electrical blocker is resolved. I don't see an active
project blocker preventing tomorrow's plastering.

USER
move it to Friday instead.

OG
That changes the planned plastering date and affects
one downstream activity.

Move plastering to Friday?

[Cancel] [Confirm]

USER
Confirm

OG
Done. I've updated the schedule and logged the change.
```

Then verify manually:

```text
Materials
→ Cement = 100

Issues
→ electrical blocker resolved

Schedule
→ plastering updated

Tasks
→ associated state correct

Activity
→ all meaningful mutations visible

OG
→ conversation remains coherent
```

Refresh.

Sign out.

Sign back in.

Everything persists.

---

# Phase Completion Protocol

Codex must follow this workflow for every phase:

```text
1. Read docs/GOLDEN_SCENARIO.md
2. Read docs/CONVERSATIONAL_OPERATIONS.md
3. Read docs/IMPLEMENTATION_STATUS.md
4. Identify active phase
5. Inspect only relevant implementation files
6. Implement active phase only
7. Run phase-specific tests
8. Run Golden Scenario regression tests
9. Fix regressions before proceeding
10. Update IMPLEMENTATION_STATUS.md
11. Report:
    - files changed
    - architecture changes
    - tests run
    - acceptance gate result
    - known issues
12. STOP
```

Do not automatically start the next phase.

---

# Implementation Status Format

Maintain:

```text
# Conversational Operations Status

Golden Scenario: PASS

Phase 0 — Audit
Status: COMPLETE

Phase 1 — Intent Router
Status: COMPLETE

Phase 2 — Project Context
Status: COMPLETE

Phase 3 — Conversational Response Layer
Status: COMPLETE

Phase 4 — Entity Resolution
Status: COMPLETE

Phase 5 — Safe Task Operations
Status: ACTIVE

...

Current blockers:
- None

Known regressions:
- None

Last verified Golden Scenario:
- timestamp
- test command
- result
```

---

# Scope Guardrails

Do not add during this implementation:

```text
billing
subscriptions
new dashboard analytics
X Layer
Vana
new construction verticals
new specialist agents without clear need
complex BIM functionality
full procurement marketplace
major frontend redesign unrelated to OG conversation
```

Those can happen after Conversational Operations is stable.

---

# Definition of Done

Conversational Operations is complete only when:

* [ ] OG responds naturally to casual conversation.
* [ ] OG answers project questions from live state.
* [ ] OG provides grounded project advice.
* [ ] OG resolves project entities reliably.
* [ ] OG can create/update/complete tasks through existing tools.
* [ ] OG can update materials through existing tools.
* [ ] OG can manage issues through existing tools.
* [ ] OG can propose schedule changes.
* [ ] Consequential changes require confirmation/approval.
* [ ] Complex site updates route into the existing Golden workflow.
* [ ] Multi-turn references work.
* [ ] All significant mutations generate activity events.
* [ ] Conversational mutations are idempotent.
* [ ] Stale conflicts are handled safely.
* [ ] Project state survives refresh/sign-in.
* [ ] No direct conversational database writes exist.
* [ ] Golden Scenario remains passing.
* [ ] Customer-facing UI consistently uses `OG Foreman` and `OG`.

---

# Final Product Thesis

OG Foreman is no longer only an agent that processes construction-site updates.

It becomes the natural-language operating layer over the entire construction project.

The user can:

**ask → understand → decide → instruct → approve → continue**

without manually navigating every project record.

But underneath the conversation, the same trusted construction system remains in control.

> **Talk to your project like you talk to your team.
> OG keeps the system current.**
