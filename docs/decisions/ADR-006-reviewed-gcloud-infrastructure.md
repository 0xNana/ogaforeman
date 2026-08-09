# ADR-006: Use reviewed gcloud scripts and authenticated Pub/Sub push

## Status

Accepted

## Date

2026-08-08

## Context

V1 needs reproducible Google Cloud resources, separate API/worker releases,
explicit IAM, dead-letter retention, backup protection, scheduler delivery, and
a rollback procedure. The repository does not yet have a Terraform state
backend or an established infrastructure module lifecycle. Eventarc's managed
Pub/Sub subscription also makes the V1 dead-letter and delivery settings less
visible to reviewers.

## Decision

Use checked-in, idempotent `gcloud` scripts for the public-beta infrastructure.
The worker receives events through a dedicated authenticated Pub/Sub push
subscription invoking a private Cloud Run service. Cloud Run IAM authenticates
the push service account, while the application validates the immutable event
envelope and persisted claim.

The explicit subscription owns its acknowledgement deadline, retry count,
dead-letter topic, and retained inspection subscription. The API and worker use
the same versioned container image but deploy as separate Cloud Run services and
entrypoints.

## Alternatives considered

### Terraform immediately

- Strong state and plan model.
- Adds backend/bootstrap/module decisions before the first staging deployment.
- Deferred until the team has a stable environment ownership and state policy.

### Eventarc Pub/Sub trigger

- Native CloudEvents delivery and less subscription setup.
- The managed subscription obscures the V1 dead-letter configuration required
  by the production-readiness contract.
- Rejected for V1; the domain event and worker boundary remain compatible with a
  later Eventarc adapter.

### Public worker endpoint with an application secret

- Simple to invoke.
- Creates a separate secret-verification boundary and unnecessary public
  exposure.
- Rejected in favor of Cloud Run IAM and OIDC-authenticated delivery.

## Consequences

- Infrastructure changes are reviewable and can be dry-run without state
  mutation.
- Operators must preserve command output and Cloud revision/evidence links;
  scripts alone do not prove a successful deployment.
- Drift detection is procedural rather than Terraform-state-driven.
- A later Terraform migration must preserve resource names, IAM boundaries,
  subscriptions, and rollback behavior documented here.
