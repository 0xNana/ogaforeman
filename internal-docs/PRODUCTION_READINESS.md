# Production Readiness Controls

This document is normative. The items below are release blockers, not optional hardening or future polish. A V1 build is not production-ready until every control has an implementation and a passing verification case.

## Control Matrix

| ID | Prototype risk | Required production control | Verification gate |
| --- | --- | --- | --- |
| PR-01 | State disappears on restart and is shared unsafely within a process | Remove `_PROJECT_DB` from runtime paths. Use repository interfaces backed by Firestore transactions. Keep an in-memory repository only for isolated tests. No request or workflow may depend on process globals. | Restart API/worker during a run; state, checkpoints, approvals, and activities remain intact. Run two concurrent project requests and prove isolation. |
| PR-02 | Repeated events create repeated blockers and requests | Require stable `event_id` and `idempotency_key`. Claim events with a Firestore create-if-absent transaction. Deduplicate equivalent open issues/requests by project, source, and normalized fingerprint. | Deliver the same event 1, 2, and 10 times; exactly one mutation set, request, notification, and report fact exists. |
| PR-03 | Approval rejection does not remove or update the pending request | Model approval and material request as linked state machines. A rejection transaction changes approval to `rejected`, request to `rejected` or `cancelled`, persists notes/resolver, emits activity, and emits no supplier action. | Approve and reject the same request in separate tests; second decision gets a version conflict; rejected requests no longer appear pending. |
| PR-04 | Approval does not resume a persisted workflow | Persist `AgentRun` checkpoint and step state as the source of pause/resume. Approval resolution publishes a continuation event that loads the checkpoint and resumes the exact workflow branch. | Stop the worker after `WAITING_FOR_APPROVAL`, restart it, resolve approval, and verify the same run completes once with no duplicate side effect. |
| PR-05 | Inventory keys are derived inconsistently from user-facing names | Give every material a canonical ID, normalized name, and unit. Resolve aliases through a repository matcher. Store quantity changes in an append-only material ledger; never derive database keys from display strings. | `Cement Bags`, `cement bags`, and a configured alias resolve to one material; mixed units and unknown aliases fail validation without mutation. |
| PR-06 | `datetime.utcnow()` produces naive timestamps | Ban naive datetimes. Use `datetime.now(UTC)` internally, Pydantic timezone-aware validation at boundaries, and Firestore timestamps at rest. | Static check rejects `utcnow`; schema tests reject naive values; serialized timestamps round-trip with timezone information. |
| PR-07 | Task updates use hard-coded keywords and task IDs | Use model structured extraction plus deterministic entity resolution against project tasks, dependency graph, and evidence. A task ID can only come from an existing project context or an explicit user selection. | New task names and paraphrases work; unrelated mentions do not mutate tasks; ambiguous matches pause for clarification. |
| PR-08 | Mentioning electrical work changes progress even when the electrician was absent | Separate fact kinds (`progress_update`, `completed_work`, `blocker`, `observation`) and require explicit positive evidence for progress. Negation/absence detection is a tested interpreter concern. | “Electrician did not come” creates a blocker/absence fact and leaves electrical progress unchanged; mixed updates update only explicitly evidenced tasks. |
| PR-09 | API workflow path bypasses the coordinator | Define one application entrypoint for event processing. API routes persist and publish events only; the worker invokes an ADK `Runner` backed by durable sessions. Typed services perform authorized mutations and `AgentRun` remains a projection. | API integration test proves a site update reaches ADK, creates one `AgentRun`, and follows the same path as Pub/Sub delivery. |
| PR-10 | Agent prompt names and sub-agent names are inconsistent | Define agent names in one typed registry. Prompt filenames, ADK `name`, descriptions, telemetry labels, and coordinator references are generated/validated from that registry. | Startup validation fails on a missing/duplicate agent; test asserts every coordinator route resolves to a registered agent. |
| PR-11 | No mutation emits an activity/audit event | Every repository mutation command requires source/actor context and commits the domain write plus `ActivityEvent` atomically. Reads and safe no-ops may emit optional activity records. | Mutation contract tests assert exactly one activity with project, actor, source event, entity, summary, and trace/run references. |
| PR-12 | No authorization, upload validation, rate limiting, structured errors, or tenant isolation | Enforce authenticated identity and active project membership in API dependencies, repositories, and tools. Validate signed uploads (type, size, checksum, project path). Add per-user/project rate limits. Return versioned error envelopes. Never query across project boundaries. | Security integration tests attempt cross-project reads/writes, forged upload metadata, oversized/unallowlisted files, burst traffic, and malformed requests. |
| PR-13 | UI uses hard-coded metrics, inline styles/scripts, and no production state model | Replace static HTML with a typed Next.js client. Read all metrics/activity/approvals from versioned APIs, handle loading/error/empty/stale states, and keep presentation separate from data fetching. | Browser tests seed two projects, verify rendered values come from API responses, and confirm a mutation updates the view after reload. |

The PR-01 and PR-04 restart gates are valid only when run against the Firestore and
Storage emulators with fresh clients. Their CI job must fail if the backing services
cannot start. An in-memory repository, process-global object dictionary, conditional
skip, or reuse of the original service/store instance is not durability evidence.

## Release Blockers

The following conditions block deployment even if the demo scenario works:

- any production request reads or writes `_PROJECT_DB`;
- an event can create a duplicate task, issue, request, report fact, notification, or external action;
- an approval decision can be applied twice or cannot resume after a process restart;
- a model can select an arbitrary task/material/project ID not present in authorized context;
- a mutation lacks an activity event or source event/actor reference;
- an unauthenticated or cross-project request can access data or media;
- a browser screen displays data that is not backed by the versioned API;
- naive timestamps, unbounded uploads, unbounded model input, or unbounded retries remain;
- safety-critical evidence can continue through a normal autonomous mutation branch.

## Required Verification Commands

The final repository must expose these checks (or documented equivalents):

```bash
pytest -q tests/unit tests/contract tests/integration tests/workflows
pytest -q tests/production_readiness
ruff check .
mypy app
cd frontend && npm run lint && npm run typecheck && npm test && npm run test:e2e
```

The production-readiness suite must include restart, concurrency, duplicate delivery, approval resume/rejection, canonical material identity, timezone validation, authorization, upload, rate-limit, and API-backed UI tests.

## Operational Evidence

Each deployed release must attach:

- test/eval results and commit SHA;
- migration and rollback notes;
- smoke-test output for API, worker, event delivery, and approval resume;
- trace links for the seeded demo run;
- known limitations with an owner and follow-up task.
