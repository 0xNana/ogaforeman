# OG Foreman Submission Architecture

This document explains the architecture presented in the All Things Agentic
Hackathon submission. The diagram is available as
[architecture-diagram.svg](architecture-diagram.svg).

![OG Foreman system architecture](architecture-diagram.svg)

## System objective

OG Foreman converts messy construction-site evidence into durable operational
work. A foreman can send text, voice, photos, or project files. The system
normalizes that evidence, uses Gemini for bounded interpretation, coordinates a
multi-step workflow under Google ADK, and applies authorized changes through
typed tools. Firestore, not model context or process memory, is the source of
truth.

The V1 product deliberately supports four workflows only:

1. Daily Site Update.
2. Material Shortage.
3. Blocker and Delay.
4. Daily Brief.

## ADK ownership boundary

**ADK owns OG's autonomous construction workflows and agentic project
conversation. Gemini reasons over authorized context, typed tools enforce and
apply mutations, and Firestore remains the source of truth.**

This claim is intentionally narrower than "every intelligent interaction runs
through ADK." Deterministic ingestion, authorization, canonical identity,
policy, validation, idempotency, and persistence remain application services.
For the Taskmaster-critical paths, ADK owns the operational control flow:

- `daily_site_update_workflow`: receive and prepare evidence, retrieve
  authorized context, interpret with Gemini, resolve canonical entities,
  fan out real progress/blocker/material analyses, join, apply policy, invoke
  typed tools, interrupt for approval, resume the same invocation, project the
  daily log, and complete;
- `delivery_delay_workflow`: retrieve the authorized project, canonical
  material request, material, and affected task context; expand downstream
  dependency impact; mark the request delayed; create a risk issue and
  source-linked follow-up task; durably send one Google Chat notification; and
  complete. The notification node succeeds only after the provider outcome is
  persisted. The
  legacy routed-event map rejects `DELIVERY_DELAYED`, so this event cannot
  bypass the dedicated ADK graph;
- `agentic_project_conversation`: classify intent, conditionally retrieve
  authorized live context, resolve referenced entities, generate a grounded
  Gemini answer, or invoke existing typed tools and confirmation/approval
  boundaries for permitted changes.

Each stage emits allowlisted telemetry containing `workflow`, `agent`, `node`,
optional `tool`, status, and duration. Prompts, raw messages, site evidence,
secrets, and chain-of-thought are excluded.

The notification boundary stays intentionally small:

```text
NotificationService
|-- LoggingNotificationProvider       local/test only
`-- GoogleChatNotificationProvider    sole real external provider
```

Both providers share the same typed contract and deterministic identity. Only
the Google Chat provider has `is_external=true`, and deployed settings reject
the logging provider.

## Runtime flow

1. A Firebase-authenticated user submits an update through the Next.js PWA.
2. The FastAPI service authorizes the user against the canonical project and
   stores original private media in Cloud Storage using a signed upload flow.
3. The API publishes a normalized `ProjectEvent` to Pub/Sub. Stable event IDs,
   delivery claims, and idempotency keys protect the at-least-once boundary.
4. An authenticated Pub/Sub push invokes the private Cloud Run worker.
5. A Google ADK `Runner` executes the registered workflow. Durable ADK session
   state supports continuation, while Firestore remains domain truth.
6. Gemini 3.6 Flash, configured through Vertex AI in deployed environments,
   performs bounded fact extraction and proposal generation. Deterministic
   services resolve canonical entities; model output cannot directly mutate
   project state.
7. Typed tools re-check identity, project authorization, evidence, confidence,
   safety policy, version preconditions, and idempotency before mutation.
8. Each successful mutation atomically emits an `ActivityEvent`. The UI reads
   projections for tasks, blockers, materials, reports, approvals, runs, and the
   activity history.
9. Safe, reversible follow-through continues automatically. Purchases,
   external commitments, financial actions, task cancellation, major schedule
   changes, and safety-critical actions pause for explicit human approval or
   escalation.
10. A manager can submit a real delivery-delay report through the authenticated
    operator endpoint. The external Google Chat send is protected by a persisted
    outbox claim, bounded retry, and deterministic provider request/message IDs.
    Missing provider configuration fails deployed startup; there is no simulator
    or deployed logging fallback. The logging provider is explicitly local/test only.

## Google technology mapping

| Requirement | Implementation |
| --- | --- |
| Gemini 3.5 or newer | Gemini 3.6 Flash through the Google Gen AI SDK; Vertex AI configuration is required in deployed environments |
| Google agent framework | Four named Google ADK workflow roots, application registration, `Runner` execution, tools, and durable session service |
| Google Cloud infrastructure | Cloud Run, Firestore, Cloud Storage, Pub/Sub, Cloud Scheduler, Cloud Build, Artifact Registry, Secret Manager, Cloud Logging, Cloud Trace, and Cloud Monitoring |
| External coordination | Google Chat incoming webhook with deterministic provider request and message IDs |
| Hosted product | Next.js web service behind Firebase Hosting; FastAPI and worker services on Cloud Run |

## Component boundaries

| Boundary | Responsibility | Key implementation area |
| --- | --- | --- |
| Next.js PWA | Authenticated project UI, multimodal capture, approvals, run and activity views | `frontend/` |
| FastAPI API | Authentication, project authorization, validation, upload signing, event creation, reads, and approval decisions | `app/api/` |
| Event transport | Durable asynchronous delivery, retry, dead-letter handling, authenticated push | `app/infrastructure/pubsub.py`, `infra/deploy.sh` |
| ADK execution | Four named workflow roots, `Runner` execution, typed runtime identifiers, and session continuation | `app/agents/adk_runtime.py`, `app/agents/site_update_execution.py`, `app/agents/event_execution.py`, `app/agents/conversation_execution.py` |
| Gemini adapter | Structured, bounded interpretation with versioned prompts and schemas | `app/infrastructure/gemini.py`, `app/prompts/` |
| Typed services and tools | Authorized, deterministic domain reads and writes | `app/services/`, `app/tools/` |
| Persistence | Firestore repositories, transactions, claims, outbox, activities, and projections | `app/repositories/` |
| Private media | Original attachment storage, verification, bounded model access | `app/infrastructure/storage.py`, `app/api/uploads.py` |
| External notification | Typed delivery payload, durable outbox, Google Chat adapter | `app/services/delivery_notifications.py`, `app/infrastructure/google_chat.py` |
| Operations | Deployment, health probes, smoke checks, backups, alerts, and rollback | `infra/`, `scripts/` |

## Reliability and safety properties

- **At-least-once delivery:** consumers claim stable event identities before
  work and safely return the persisted result on duplicate delivery.
- **Atomic audit trail:** a domain mutation and its `ActivityEvent` share one
  transaction.
- **Persisted approval boundary:** approval state plus the original ADK app,
  session, invocation, and workflow IDs are durable. Production restart safety
  is claimed only after the deployed worker-restart gate passes.
- **Versioned resumability risk:** ADK `ResumabilityConfig` is experimental, so
  the repository pins the tested ADK version. An upgrade cannot ship until the
  backed restart gate and deployed worker-replacement proof pass again.
- **Layered authorization:** the API, repositories, and tools all enforce the
  canonical project and user boundary.
- **Bounded model authority:** Gemini returns typed interpretations and
  proposals. Deterministic code validates and mutates.
- **Fail-closed language handling:** negated or ambiguous statements cannot
  complete work.
- **Human control:** consequential or safety-critical actions never inherit an
  automatic approval.
- **Private evidence:** media is private by default; signed access is short
  lived and workers re-read verified objects rather than trusting browser state.
- **Operational correlation:** `request_id`, `event_id`, `run_id`, `trace_id`,
  project ID, workflow name, agent name, tool name, and prompt version provide
  end-to-end correlation without exposing prompts, secrets, or hidden reasoning.
- **Build provenance:** the public `/api/v1/version` response, Cloud Run's latest
  ready revision, stamped Git SHA/build time/version, and resolved image digest
  must agree before deployment evidence passes.

## Deployment topology

The reviewed deployment creates separate Cloud Run services for the web, API,
and worker. The API is public but application routes require Firebase identity.
The worker is private and accepts authenticated Pub/Sub push. Each workload has
a dedicated service account and scoped IAM. Firestore and Storage are protected
with checked-in rules, private access, deletion protection, versioning, backup,
and retention controls. Rollback changes Cloud Run traffic to a previously
verified immutable revision; it does not rewrite durable project state.

## Evidence standard

The architecture diagram describes the intended submission runtime, but a
diagram is not deployment proof. Before submission, the video and testing
record must show all of the following against the same current commit:

- the public application and authenticated workflow execution;
- `/api/v1/version` reporting the submitted full Git SHA and current API
  revision, plus Cloud Run web, API, and worker revisions and resolved image
  digests from the generated provenance artifact;
- a live Gemini-backed run, not fake-model or deterministic `/demo` output;
- Firestore changes, `ActivityEvent` audit entries, and run status updates;
- an approval pause and continuation for a consequential action;
- correlated Cloud Logging or Cloud Trace evidence for the same run.

Current release gates and the exact evidence still required are tracked in
[SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) and
[TESTING.md](TESTING.md).

## Design references

- [Public architecture contract](../ARCHITECTURE.md)
- [Agent design](../AGENT_DESIGN.md)
- [Production agent inventory](AGENT_INVENTORY.md)
- [Workflow state machines](../WORKFLOWS.md)
- [Tool contracts](../TOOL_CONTRACTS.md)
- [Security and safety](../SECURITY_SAFETY.md)
- [Deployment contract](../DEPLOYMENT.md)
- [Official competition rules](https://allthingsagentichackathon.devpost.com/rules)
