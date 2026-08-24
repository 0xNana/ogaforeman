# OG Foreman Documentation

This directory contains the public product, architecture, contract, operations, and release documentation for OG Foreman. It is the authoritative reference for the production-ready V1 service boundary and verification bar.

## Read Order

1. [PRODUCT.md](PRODUCT.md) - product promise, users, scope, requirements, and V1 acceptance criteria.
2. [ENGINEERING_SPEC.md](ENGINEERING_SPEC.md) - stack, commands, project structure, coding rules, and global definition of done.
3. [ARCHITECTURE.md](ARCHITECTURE.md) - runtime boundaries, request/event flows, persistence, and deployment topology.
4. [AUTH.md](AUTH.md) - human identity, canonical users, project roles, browser sessions, and workload authentication.
5. [DOMAIN_MODEL.md](DOMAIN_MODEL.md) - entities, invariants, Firestore layout, and lifecycle rules.
6. [EVENT_SCHEMA.md](EVENT_SCHEMA.md) - normalized `ProjectEvent` envelope and delivery semantics.
7. [AGENT_DESIGN.md](AGENT_DESIGN.md) - production workflow roots, model boundaries, structured outputs, and confidence policy.
8. [TOOL_CONTRACTS.md](TOOL_CONTRACTS.md) - deterministic read and mutation interfaces.
9. [WORKFLOWS.md](WORKFLOWS.md) - the four V1 workflow state machines.
10. [API.md](API.md) - HTTP contracts consumed by the web application and integrations.
11. [SECURITY_SAFETY.md](SECURITY_SAFETY.md) - authorization, AI safety, construction escalation, and data controls.
12. [SLOS.md](SLOS.md) - public-beta service, recovery, backup, and capacity targets.
13. [DEPLOYMENT.md](DEPLOYMENT.md) - local environments, Google Cloud resources, CI/CD, and rollback.
14. [OPERATIONS.md](OPERATIONS.md) - observability, alerts, failure recovery, and support procedures.
15. [Submission package](submission/ARCHITECTURE.md) - hackathon architecture,
production agent inventory, Devpost copy, and judge testing instructions.
The executable plan and implementation checklist are maintained separately from this public contract index.

## Canonical Ownership

- Product scope and user-facing behavior: [`PRODUCT.md`](PRODUCT.md).
- System and API contracts: [`AUTH.md`](AUTH.md), [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md), [`EVENT_SCHEMA.md`](EVENT_SCHEMA.md), [`TOOL_CONTRACTS.md`](TOOL_CONTRACTS.md), and [`API.md`](API.md).
- Security, safety, and abuse policy: [`SECURITY_SAFETY.md`](SECURITY_SAFETY.md).
- Release blockers, evaluation thresholds, UX acceptance, and deterministic demo evidence are maintained by the engineering release process.
- Service objectives and recovery targets: [`SLOS.md`](SLOS.md).
- Current implementation evidence is maintained in the engineering status record.

## Architecture decisions

- [ADR-001: Google-first runtime](decisions/ADR-001-google-first-runtime.md)
- [ADR-002: Firestore source of truth](decisions/ADR-002-firestore-source-of-truth.md)
- [ADR-003: At-least-once idempotent events](decisions/ADR-003-at-least-once-idempotent-events.md)
- [ADR-004: Approval and safety boundaries](decisions/ADR-004-approval-and-safety-boundaries.md)
- [ADR-005: Versioned API and Next.js client](decisions/ADR-005-versioned-api-and-nextjs-client.md)
- [ADR-006: Reviewed gcloud infrastructure](decisions/ADR-006-reviewed-gcloud-infrastructure.md)
- [ADR-007: Deployment build provenance](decisions/ADR-007-deployment-build-provenance.md)

## Document Authority

When documents conflict, use this precedence:

1. Safety and approval constraints in `SECURITY_SAFETY.md`.
2. Product scope and acceptance criteria in `PRODUCT.md`.
3. Typed contracts in `AUTH.md`, `DOMAIN_MODEL.md`, `EVENT_SCHEMA.md`, `TOOL_CONTRACTS.md`, and `API.md`.
4. Accepted architecture decisions in `decisions/`.
5. Execution ordering in `tasks/plan.md`.
6. Current implementation evidence and release records.

Do not resolve a conflict only in code. Update the controlling document first.

## Status Vocabulary

- `Accepted`: the build should follow this decision.
- `Proposed`: usable as the default, but still open to a product or technical decision.
- `Deferred`: intentionally outside V1.
- `Superseded`: retained for history but replaced by a newer decision.

## Maintenance Rule

At the end of every implementation phase:

- update the implementation status record and the project checklist;
- record any changed contract before changing consumers;
- add or supersede an ADR for expensive-to-reverse decisions;
- add tests and eval cases for changed behavior;
- record known limitations rather than hiding them in prompts or comments.
