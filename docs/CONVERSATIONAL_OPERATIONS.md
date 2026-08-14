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
