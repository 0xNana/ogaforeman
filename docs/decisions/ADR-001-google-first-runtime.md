# ADR-001: Use Google ADK and Managed Google Runtime

## Status

Accepted

## Context

The product depends on structured agent reasoning, workflow fan-out/fan-in, retries, state, and human approval pauses. Recreating those primitives would increase risk and make the hackathon less representative of the intended architecture.

## Decision

Use Google ADK 2.x for coordinator/specialist agents and workflow orchestration. Deploy the API and worker on Cloud Run, use Firestore for state, Cloud Storage for media, Pub/Sub/Eventarc for events, and Cloud Logging/Trace for observability.

## Consequences

- The team must follow ADK's workflow/checkpoint primitives instead of adding a custom orchestration engine.
- Cloud emulator/fake adapters are required for local tests.
- Deployment is Google-specific in V1, but domain/application layers remain provider-agnostic behind interfaces.
