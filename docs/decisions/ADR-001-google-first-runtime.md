# ADR-001: Use Google ADK and Managed Google Runtime

## Status

Accepted

## Context

The product depends on structured agent reasoning, workflow fan-out/fan-in, retries, state, and human approval pauses. Recreating those primitives would increase risk and make the hackathon less representative of the intended architecture.

## Decision

Use Google ADK 2.x Runner/SessionService for agentic execution and workflow orchestration. Deploy the API and worker on Cloud Run, use Firestore for state, Cloud Storage for media, Pub/Sub/Eventarc for events, and Cloud Logging/Trace for observability. Legacy route maps and manual resume code are migration-only and are not execution authority.

## Consequences

- The team must follow ADK's workflow/checkpoint primitives instead of adding a custom orchestration engine.
- Cloud emulator/fake adapters are required for local tests.
- Deployment is Google-specific in V1, but domain/application layers remain provider-agnostic behind interfaces.

## Responsibility boundaries

All AI-mediated, autonomous, event-driven, and resumable workflows in OG
Foreman execute through Google ADK and an ADK Runner. Deterministic
application operations may invoke domain services directly when no agent
reasoning or orchestration is required. Firestore remains canonical
construction-domain state; ADK owns agent execution state; domain services own
authoritative mutations.

Google ADK is OG Foreman's sole agent orchestration runtime. ADK owns workflow
execution, durable session/runtime state, node routing, HITL interruption and
resume, runtime retries, and workflow observability.

Firestore remains authoritative for construction truth: projects, tasks,
issues, materials, requests, approvals, reports, attachments, and activities.
OG Foreman domain services own authorization, canonical identity, business state
transitions, business idempotency, and typed mutations. `AgentRun` and
`ActivityEvent` are product/audit projections of execution, not a competing
workflow engine.

Future custom orchestration requires a superseding ADR with evidence that the
supported ADK runtime cannot satisfy the requirement. A custom cursor,
checkpoint store, pause marker, retry scheduler, or next-step dispatcher must
not be added under ADR-001.

## Verification evidence

The native site-update graph exposes named node transitions for input receipt,
multimodal preparation, interpretation, progress/blocker/material fan-out,
fan-in, action composition, policy evaluation, tool execution, daily-log
projection, activity emission, and completion. The authorized AgentRun API
exposes the ADK session, invocation, workflow, and trace identifiers needed to
correlate those events without exposing private model reasoning.
