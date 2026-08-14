## P0 — Finish Phase 17

## Implementation status

| Step | Status | Evidence |
| --- | --- | --- |
| P0.1 Action Composer | Complete | Typed `ActionComposer` output and fail-closed unit coverage. |
| P0.2 Typed mutation dispatch | Complete | Conversation API integration tests execute existing task, material, and issue services. |
| P0.3 Pending-command wiring | Complete | Signed typed commands persist in `ConversationMemory` with audited lifecycle transitions. |
| P0.4 Proposal identity and versions | Complete | Server-derived IDs, signatures, entity/memory CAS, and durable confirmation fencing. |
| P0.5 Confirm/cancel APIs | Complete | Idempotent server-only confirm/cancel endpoints with stale, replay, expiry, collision, and restart coverage. |
| P0.6 Purchase approval handoff | Complete | Exact-quantity request, approval, waiting run, replay, approval resume, supplier simulation, and terminal cleanup use the existing workflow. |
| P0.7 Major schedule approval | Complete | Signed approval-bound commands use the existing approval outbox/worker, resolver checks, typed schedule CAS, atomic activity emission, and idempotent replay. |
| P0.8 Drawer proposal controls | Complete | Drawer reloads durable server proposals and sends only the proposal ID plus observed memory version to accessible Confirm/Cancel controls. |
| P0.9 Runtime conversational evals | Active | All production conversation routes are now available to the runtime harness. |
| P0.10 Golden Flow | Pending | Final API, Firestore restart, and browser gate. |

### 1. Build the Action Composer

This is the missing bridge.

Input:

```text
model interpretation
+
authorized project context
+
resolved entities
+
mutation policy
```

Output must be a typed command, never free-form JSON invented downstream:

```text
TaskCommand
MaterialCommand
IssueCommand
ScheduleCommand
PurchaseCommand
```

Example:

```text
USER
"we've got 100 bags of cement now"

        ↓

ActionComposer

        ↓

UpdateMaterialQuantityCommand(
    material_id="mat_cement",
    quantity=100,
    unit="bags",
    observed_version=7
)
```

The composer should **not execute anything**.

It proposes the domain command.

---

## 2. Wire conversation API → typed mutation services

This is the real milestone.

Today you apparently have:

```text
chat
→ model
→ response
```

We need:

```text
chat
→ intent
→ entity resolution
→ action composer
→ policy
→ typed domain service
→ persistence
→ ActivityEvent
→ OG response
```

Reuse:

```text
TaskService / TaskTool
MaterialService / MaterialTool
IssueService / IssueTool
ScheduleService / ScheduleTool
```

No chat-specific database mutation code.

---

# 3. Make `pending_command` real

These existing pieces:

```text
pending_command
remember_command()
require_command()
clear_command()
```

having **zero production callers** means the confirmation architecture currently exists only on paper.

Connect them.

For `CONFIRM_FIRST`:

```text
User:
"Move plastering to Friday"

        ↓

ActionComposer
        ↓
ScheduleChangeCommand

        ↓

Policy = CONFIRM_FIRST

        ↓

remember_command(command)

        ↓

return server proposal
```

Conversation state:

```text
pending_command = {
    proposal_id,
    command_type,
    payload,
    project_id,
    created_by,
    observed_entity_version,
    observed_memory_version,
    created_at,
    expires_at
}
```

No mutation yet.

---

# 4. Server-issued proposal IDs + versions

This is essential.

Never let the browser tell the server:

> “Execute that schedule command we discussed.”

The server issues:

```text
proposal_id
```

along with:

```text
observed_entity_version
observed_memory_version
```

Then:

```text
POST /conversation/proposals/{proposal_id}/confirm
```

The server:

1. loads proposal
2. loads current project state
3. verifies version
4. verifies user permission
5. reruns necessary policy checks
6. executes typed command
7. marks proposal consumed
8. clears pending command
9. logs ActivityEvent

If state changed:

```text
409 STALE_PROPOSAL
```

OG responds:

> The project changed since I proposed that. I’ve refreshed the plan.

This builds directly on the stale-approval behavior you already proved elsewhere.

---

# 5. Implement Confirm / Cancel APIs

Something along the lines of:

```text
POST /api/v1/conversations/{conversation_id}/proposals/{proposal_id}/confirm

POST /api/v1/conversations/{conversation_id}/proposals/{proposal_id}/cancel
```

### Confirm

```text
PENDING
→ validate
→ execute
→ EXECUTED
```

### Cancel

```text
PENDING
→ CANCELLED
```

Both should be idempotent.

Repeated confirmation must **not execute twice**.

---

# 6. Material purchase must route into existing approval workflow

This is especially important.

These are two different intents:

```text
"We have 100 bags of cement."
```

Safe material-state update.

Versus:

```text
"Buy 100 bags of cement."
```

Consequential financial action.

That second one should produce something like:

```text
CreateMaterialPurchaseRequestCommand
```

Then:

```text
conversation
→ command
→ policy = APPROVAL_REQUIRED
→ existing MaterialRequest
→ existing Approval
→ existing WAITING_FOR_APPROVAL
→ approve/reject
→ existing resume path
```

**Do not create a second conversational approval framework.**

The whole point is to reuse the Golden Scenario machinery.

---

# 7. Major schedule changes use the same principle

For example:

```text
"Move the foundation works back two weeks."
```

should become:

```text
ScheduleChangeCommand
```

then impact analysis:

```text
affected tasks
dependencies
project completion impact
```

Policy may resolve to:

```text
CONFIRM_FIRST
```

for a small local change, or:

```text
APPROVAL_REQUIRED
```

for a major change.

Then use the existing approval infrastructure.

---

# 8. Only then add drawer Confirm / Cancel

Backend first.

Then UI.

OG drawer should receive a structured proposal:

```text
PROPOSED CHANGE

Plastering
Thu 14 Aug → Fri 15 Aug

Impact
Painting preparation shifts one day.

[Cancel]           [Confirm]
```

Clicking Confirm sends only:

```text
proposal_id
expected_version
```

Not the whole mutation payload from the browser.

That keeps the server authoritative.

---

# 9. Runtime conversational evals

Current static/unit evaluation isn't enough.

Create runtime cases against the actual conversational pipeline:

```text
"what's up?"
→ query/no mutation

"we have 100 bags now"
→ MaterialService called

"mark plumbing complete"
→ TaskService called

"electrical is sorted"
→ IssueService called

"move plastering to Friday"
→ pending proposal, NO mutation

"confirm"
→ proposal executes

"buy 100 bags cement"
→ Approval created, NO purchase yet
```

Also test:

```text
duplicate confirm
stale proposal
cancelled proposal
unauthorized command
ambiguous entity
expired proposal
```

---

# 10. Then run the Phase 17 Golden Flow

This is the final gate.

```text
USER
yo OG, what's up?

OG
Blockwork is done. Electrical is still blocked and
the cement request needs you.

USER
how much cement do we have?

OG
10 bags.

USER
delivery came. we've got 100 now.

        ↓

Material quantity really becomes 100.

USER
electrical is sorted.

        ↓

Issue really resolves.

USER
wdyt about plastering tomorrow?

        ↓

Advice only. No mutation.

USER
move it to Friday.

        ↓

Server creates proposal.
Schedule unchanged.

OG
That affects one downstream activity.

[Cancel] [Confirm]

USER clicks Confirm.

        ↓

proposal validated
schedule service executes
activity created
proposal consumed
```

Then:

**refresh → sign out → sign in → same state.**

---

##  Execution order

```text
P0.1 Action Composer
P0.2 Conversation → typed mutation services
P0.3 Pending-command production wiring
P0.4 Proposal IDs + optimistic versions
P0.5 Confirm/cancel APIs
P0.6 Material purchase → existing approval workflow
P0.7 Major schedule change → approval workflow
P0.8 Drawer proposal UI
P0.9 Runtime conversational evals
P0.10 Browser/API Golden Flow + restart persistence
```

> **Do not add another conversational capability until all ten pass.**

The biggest architectural insight here is that we **already have the hard part** from the original Golden Scenario: typed project services, durable state, approval, resume, conflict handling, and audit.

Phase 17 is mostly about finally connecting conversational OG to that trusted machinery.

Once that integration is complete, OG stops being “a chatbot that understands construction” and becomes what we actually want:

> **a conversational control plane over a real construction PM.**
