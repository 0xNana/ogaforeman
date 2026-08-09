# Oga Foreman Documentation

This directory turns `high-level.md` into the build contract for Oga Foreman. The documents describe the target product, the current prototype gap, the interfaces between components, and the verification bar for a finished V1.

## Read Order

1. [PRODUCT.md](PRODUCT.md) - product promise, users, scope, requirements, and V1 acceptance criteria.
2. [ENGINEERING_SPEC.md](ENGINEERING_SPEC.md) - stack, commands, project structure, coding rules, and global definition of done.
3. [STATUS.md](STATUS.md) - what exists today and what is still a prototype.
4. [ARCHITECTURE.md](ARCHITECTURE.md) - runtime boundaries, request/event flows, persistence, and deployment topology.
5. [AUTH.md](AUTH.md) - human identity, canonical users, project roles, browser sessions, and workload authentication.
6. [DOMAIN_MODEL.md](DOMAIN_MODEL.md) - entities, invariants, Firestore layout, and lifecycle rules.
7. [EVENT_SCHEMA.md](EVENT_SCHEMA.md) - normalized `ProjectEvent` envelope and delivery semantics.
8. [AGENT_DESIGN.md](AGENT_DESIGN.md) - coordinator and specialist responsibilities, structured outputs, and confidence policy.
9. [TOOL_CONTRACTS.md](TOOL_CONTRACTS.md) - deterministic read and mutation interfaces.
10. [WORKFLOWS.md](WORKFLOWS.md) - the four V1 workflow state machines.
11. [API.md](API.md) - HTTP contracts consumed by the web application and integrations.
12. [UI_UX.md](UI_UX.md) - responsive product flows, screens, states, and accessibility requirements.
13. [SECURITY_SAFETY.md](SECURITY_SAFETY.md) - authorization, AI safety, construction escalation, and data controls.
14. [EVALS.md](EVALS.md) - test pyramid, AI evaluation cases, and release thresholds.
15. [SLOS.md](SLOS.md) - public-beta service, recovery, backup, and capacity targets.
16. [DEPLOYMENT.md](DEPLOYMENT.md) - local environments, Google Cloud resources, CI/CD, and rollback.
17. [OPERATIONS.md](OPERATIONS.md) - observability, alerts, failure recovery, and support procedures.
18. [DEMO.md](DEMO.md) - deterministic hackathon demo, seed data, and reset requirements.
19. [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) - mandatory controls for replacing the prototype safely.
20. [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) - phase overview and links to executable tasks.
21. [TRACEABILITY.md](TRACEABILITY.md) - requirement-to-workflow, API, UI, and test mapping.

The executable plan lives in [`../tasks/plan.md`](../tasks/plan.md), and the working evidence checklist lives in [`../tasks/todo-v1.md`](../tasks/todo-v1.md).

## Architecture decisions

- [ADR-001: Google-first runtime](decisions/ADR-001-google-first-runtime.md)
- [ADR-002: Firestore source of truth](decisions/ADR-002-firestore-source-of-truth.md)
- [ADR-003: At-least-once idempotent events](decisions/ADR-003-at-least-once-idempotent-events.md)
- [ADR-004: Approval and safety boundaries](decisions/ADR-004-approval-and-safety-boundaries.md)
- [ADR-005: Versioned API and Next.js client](decisions/ADR-005-versioned-api-and-nextjs-client.md)
- [ADR-006: Reviewed gcloud infrastructure](decisions/ADR-006-reviewed-gcloud-infrastructure.md)

## Document Authority

When documents conflict, use this precedence:

1. Safety and approval constraints in `SECURITY_SAFETY.md`.
2. Product scope and acceptance criteria in `PRODUCT.md`.
3. Typed contracts in `AUTH.md`, `DOMAIN_MODEL.md`, `EVENT_SCHEMA.md`, `TOOL_CONTRACTS.md`, and `API.md`.
4. Accepted architecture decisions in `decisions/`.
5. Execution ordering in `tasks/plan.md`.
6. The original `high-level.md` brief.

Do not resolve a conflict only in code. Update the controlling document first.

## Status Vocabulary

- `Accepted`: the build should follow this decision.
- `Proposed`: usable as the default, but still open to a product or technical decision.
- `Deferred`: intentionally outside V1.
- `Superseded`: retained for history but replaced by a newer decision.

## Maintenance Rule

At the end of every implementation phase:

- update `STATUS.md` and `tasks/todo-v1.md`;
- record any changed contract before changing consumers;
- add or supersede an ADR for expensive-to-reverse decisions;
- add tests and eval cases for changed behavior;
- record known limitations rather than hiding them in prompts or comments.
