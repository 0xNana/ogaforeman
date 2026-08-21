# Conversational Operations Architecture

## Existing components reused

- `SiteUpdateIntakeService` persists authenticated intake, the event, outbox message, and run.
- `process_event` and ADK site-report execution coordinate the Golden workflow.
- project-context and entity-resolution services provide authorized, bounded project facts.
- task, issue, material, report, approval, and activity services own validated mutations.
- approval continuation reloads persisted state and guards external simulation.
- the global Ask OG composer already supplies text, voice, photo, and attachment input.

## Phase 1 additions

- `IntentDecision` is the typed classification contract.
- `IntentClassifier` isolates the model boundary; `GeminiIntentClassifier` requests structured
  output and `FakeIntentClassifier` provides deterministic tests and evals.
- `IntentRoutingService` validates conversational context and maps decisions to destinations.
- `SITE_UPDATE` maps to `GOLDEN_SITE_UPDATE`; channel integration must submit it through
  `SiteUpdateIntakeService`, never through chat-specific fact mutations.

```text
message
→ IntentClassifier
→ IntentRoutingService
  ├─ casual response
  ├─ project context (implemented in Phase 2)
  ├─ advice (later phase)
  ├─ project action (later phase)
  ├─ clarification / confirmation (later phase)
  └─ Golden site-update intake (existing workflow)
```

The router decides only the destination. It does not retrieve project records, interpret site
facts, execute tools, persist conversation state, or mutate project state.

## Duplicate-orchestration risks

- Do not extract task, material, or issue facts in the intent prompt.
- Do not add a conversational database adapter or direct Firestore writes.
- Do not create a second approval, confirmation, or site-update state machine.
- Do not accept bare confirmation or clarification replies without persisted pending context.
- Do not allow a low-confidence mutation decision to enter an action destination.

## Extension points

Phase 2 implements authorized, query-shaped context retrieval behind the `PROJECT_CONTEXT`
destination. It exposes bounded typed projections, uses project-local dates for today/tomorrow,
loads only selected domains, and treats persisted repositories as truth. Phase 3 formats those
facts into concise deterministic replies with honest empty states and internal grounding refs.
It refuses operational destinations, so Golden site updates and future actions cannot be consumed
as chat responses. Later phases may connect mutation destinations to existing typed services only
after entity resolution and explicit policy checks exist.

Phase 4 adds a project-scoped entity-resolution boundary for every documented conversational
entity. Canonical IDs and contextual references are reloaded from the requested entity repository;
material aliases resolve to the existing canonical material; fuzzy matches require a high score
and a clear margin. Ambiguous and unknown results are non-actionable and carry only bounded
clarification candidates. Resolution itself is read-only.

Phase 5 adds a thin conversational task-operation service over the existing typed Task service.
It accepts only resolved project-scoped task/member identities, then delegates creation, status,
completion, assignment, priority, and note changes to domain commands. Those commands enforce
permissions and state policy and atomically persist one task version with one activity event.
Idempotency keys replay the persisted result; conversational code never writes directly.

Phase 6 composes the typed Material service for creation, absolute stock counts, required
quantities, notes, and delivery receipt. Absolute counts remain transaction-safe and append-only
in the material ledger. Partial deliveries accumulate on their resolved material request, while a
full-delivery transition requires the cumulative approved quantity. Statements combining shortage
and schedule risk are handed back to the existing material-risk workflow instead of duplicating it.

Phase 7 composes typed Issue commands for creation, assignment, routine status changes, resolution,
and notes. Resolved issue/member identities are revalidated at the repository boundary, positive
evidence gates resolution, and each idempotent mutation atomically emits its activity event.

Phase 8 adds a deterministic mutation-policy boundary. Typed mutation kinds map to routine,
confirmation, existing-approval, or deny/escalate classes; authorization and project scope are
inputs, while arbitrary model safety judgments are not.

Phase 9 adds dependency-aware schedule proposals. The service resolves the selected task, computes
downstream impact, applies mutation policy, and returns a confirmation prompt without writing.
Only a confirmed routine proposal executes; selected and downstream dates persist atomically with
one replay-safe schedule activity. Major changes remain on the approval-required path.

Phase 10 routes text/chat site facts through a typed `ConversationSiteUpdateRouter` into the
existing `SiteUpdateIntakeService`, preserving durable event, outbox, AgentRun, coordinator, and
Golden workflow behavior without duplicating fact interpretation or mutations.

Phase 11 adds a read-only advice service over authorized context. Recommendations cite persisted
task, issue, and material records, distinguish proceed/hold/review, and cannot authorize a write.

Phase 12 stores only bounded entity pointers and pending conversation context in a project- and
user-scoped Firestore record. A pointer is resolved again through the authorized entity resolver
before use; missing or changed records cannot be revived from chat history.

Phase 13 adds `POST /api/v1/projects/{project_id}/conversations/messages` and connects it to the
global Ask OG drawer. The response contract discriminates normal replies, advice, proposed
changes, clarifications, and Golden workflow handoffs. Voice, photo, and attachment intake remains
the existing `SiteComposer` inside the drawer rather than a second media path.

Phase 14 records observable `conversation.mutation_requested` and
`conversation.confirmation_requested` transitions with bounded reason codes. Existing typed
domain services continue to own mutation and approval activities; prompts, raw chat content,
chain-of-thought, and secrets are excluded.

Phase 15 carries optional expected versions into conversational task, material, and issue
commands. Replayed idempotency scopes return the prior result, while stale commands raise a
conflict and preserve the latest persisted value.

The conversational UX correction adds a non-mutating `HELP` destination backed by implemented
product knowledge, plus a deterministic persisted project-setup projection. Bounded product-help
utterances are answered after user authentication but before project authorization, memory, storage,
or Gemini access. `POST /api/v1/conversations/messages` makes the no-project setup state reachable
and resolves a sole authorized project without weakening project-scoped access. Cancelled tasks do
not contribute to readiness, schedule presence, or task counts. The API identifies assistant responses as `OG`; intent and
response categories remain diagnostic metadata and are never rendered as conversation authors.
