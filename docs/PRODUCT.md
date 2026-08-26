# Product Specification: OG Foreman Production-Ready V1

## Status

Accepted for a production-ready public beta. The hackathon scenario is the first deterministic acceptance fixture, not a reduced reliability standard.

## Assumptions

These assumptions make the product brief implementable. Change them explicitly if they are wrong.

1. V1 is a responsive web application, not a native mobile application.
2. The hackathon demo uses one seeded organization and project, while the data model remains multi-project and multi-user.
3. Firestore is the production source of truth; the current in-memory `_PROJECT_DB` is prototype-only.
4. The Python/FastAPI backend remains the service boundary and Google ADK remains the agent/workflow runtime.
5. A Next.js TypeScript application replaces the static `web/index.html` dashboard.
6. Voice transcription and photo understanding use managed Google model capabilities; raw media is stored in Cloud Storage.
7. OG prepares and tracks approved material requests but does not send money or
   create a binding supplier order. Supplier status is never fabricated.
8. Authentication may run in seeded demo mode locally; a deployable environment uses Firebase Authentication or Google Identity Platform.
9. All dates are stored in UTC and rendered in the project's configured timezone.
10. English is the initial interface and extraction language. The contracts must not prevent later multilingual input.

## Product Promise

> Tell OG what happened on site. OG handles the follow-through.

OG Foreman converts unstructured construction-site events into verified project state changes and operational follow-through. It is not a general project-management dashboard and not a chat assistant that waits for every next instruction.

## Primary Users

### Site Foreman

- submits voice, text, photos, and files from a phone;
- needs confirmation that the update was understood;
- should not need to navigate a complex project-management system.

### Project Manager

- reviews blockers, material risks, and schedule impact;
- approves or rejects high-impact actions;
- needs an audit trail of what OG did and why.

### Project Administrator

- creates projects, members, tasks, dependencies, materials, and thresholds;
- maintains the project state that OG reasons over.

### Demo Judge or Stakeholder

- must see event-driven autonomy, human control, and technical traceability in under four minutes.

## V1 Workflows

Only these workflows are core V1 scope:

| Workflow | Trigger | Required outcome |
| --- | --- | --- |
| Daily Site Update | Voice, text, photos, or file | Persist input, extract facts, update safe project state, create issues/requests, refresh report, and show activity |
| Material Shortage | Extracted material fact or stock event | Calculate shortage, prepare request, pause for approval when required, resume and track status |
| Blocker and Delay | Extracted blocker or overdue task | Resolve affected task/dependencies, calculate impact, assign or escalate, and monitor resolution |
| Daily Brief | Scheduled project event | Summarize progress, blockers, material risks, pending approvals, and next work without a user prompt |

## Functional Requirements

### FR-01 Project Setup

- An administrator can create a project with name, location, dates, timezone, description, and status.
- An administrator can add members with `admin`, `manager`, or `foreman` roles.
- An administrator can create tasks and task dependencies.
- An administrator can define material stock, units, minimum quantities, and approval thresholds.

### FR-02 Site Update Intake

- A foreman can submit text, record or upload audio, and attach multiple photos/files.
- The API acknowledges accepted input quickly and processes it asynchronously.
- The original media, transcript, submitter, project, timestamps, and checksum are retained.
- Re-delivering the same event does not duplicate state changes.

### FR-03 Interpretation

- OG extracts completed work, progress, blockers, material observations, risks, and other observations into a typed schema.
- Every extracted fact includes evidence, confidence, and whether clarification is required.
- Ambiguous completion language does not complete a task.
- Unsupported facts remain observations and do not mutate project state.

### FR-04 Project Context and Matching

- OG retrieves only the relevant project, active tasks, dependencies, recent updates, materials, open issues, and pending approvals.
- Extracted facts are matched to known entities with a confidence score.
- Low-confidence entity matches create a clarification item rather than a guessed mutation.

### FR-05 Safe Autonomous Actions

- OG may create reports, activities, issues, routine notifications, and proposed tasks.
- OG may update task progress when evidence and confidence meet the configured policy.
- Every mutation is made by a typed deterministic tool and produces an `ActivityEvent`.
- OG cannot mutate the database directly from model output.

### FR-06 Approval Actions

- Purchases, external commitments, task cancellation, major schedule changes, and financial actions require approval.
- Approval records preserve the proposal, reason, evidence, requester, resolver, and timestamps.
- Approval resolution is idempotent and resumes the correct paused workflow.
- Rejection produces no downstream commitment and records the decision.

### FR-07 Material Follow-through

- Material need is calculated from available quantity and upcoming task requirement.
- A shortage creates one material request per idempotency scope.
- The user can approve or reject the request from the command center.
- An authenticated operator can report a real revised delivery date and reason
  against an approved canonical request. The resulting event records the delay,
  dependency impact, risk, follow-up, and external notification.

### FR-08 Blocker Follow-through

- A blocker is tied to one or more tasks when evidence supports the link.
- Dependency traversal identifies directly affected downstream tasks.
- The workflow records projected delay with its assumptions.
- High or critical safety/structural issues stop autonomous project mutations and escalate to a qualified human.

### FR-09 Daily Brief

- A scheduled event generates one brief per project and reporting window.
- The brief includes achievements, blockers, risks, approvals, overdue work, and next 24-hour focus.
- Empty sections are omitted or stated plainly; the model must not invent site activity.

### FR-10 Activity and Explainability

- The user can inspect each run from trigger through interpretation, tools, approval waits, retries, and completion.
- User-facing activity describes business actions, not raw chain-of-thought.
- User-facing OG prose uses project and record names, never canonical database IDs; IDs remain available only in typed grounding and audit metadata.
- Technical trace IDs link the UI run to Cloud Logging and Cloud Trace.

### FR-11 Notifications

- Routine in-app notifications are generated for assignments, approvals, delay risks, and workflow failures.
- Duplicate retries do not send duplicate notifications.
- Delivery delays always persist their risk, follow-up, in-app activity, and a
  replay-safe external-delivery outcome. Staging may temporarily select the
  explicit `disabled` provider and record that outcome as skipped; it must never
  represent a skipped delivery as sent. Production requires a configured real
  external provider. The local/test `logging` provider remains development-only.

### FR-12 Reporting

- Site updates feed a daily report for the project date.
- Reprocessing an event updates the existing report deterministically rather than appending duplicate facts.
- Reports retain source links to the site updates and activity events that produced them.

## Non-Functional Requirements

| Area | V1 target |
| --- | --- |
| Intake acknowledgement | p95 under 1 second, excluding media upload |
| Text-only workflow | p95 under 15 seconds in deployed demo conditions |
| Availability | 99.5% monthly public-beta objective; see `SLOS.md` |
| Idempotency | Zero duplicate domain mutations for the same event ID/idempotency key |
| Auditability | 100% of mutations linked to actor, event, workflow run, and activity |
| Accessibility | WCAG 2.2 AA for core web flows |
| Responsive UI | Fully usable at 360 px width and desktop at 1440 px |
| Security | Project-scoped authorization on every read/write endpoint |
| Data durability | No production state kept only in process memory or ADK session memory |
| Recovery | RPO zero for acknowledged domain writes; RTO 60 minutes; failed events retry then dead-letter |

## Autonomy Policy

### OG May Act Automatically

- update records with validated evidence;
- record reported progress;
- create issues, tasks, reports, activities, and routine notifications;
- prepare material requests;
- flag schedule and material risks.

### OG Must Request Approval

- purchases or supplier submission;
- major schedule changes;
- external commitments;
- financial actions;
- task cancellation;
- high-impact project changes.

### OG Must Stop and Escalate

- possible structural failure;
- serious safety hazard or injury;
- instruction to conceal, falsify, or backdate records;
- action outside the user's project or authority;
- evidence conflicts that could cause a high-impact mutation.

## Explicitly Out of Scope

- payroll, accounting, invoicing, billing, credits, subscriptions, or paid tiers;
- tendering, estimating, contractor CRM, procurement marketplaces, or supplier payments;
- BIM authoring, drawing interpretation, engineering certification, or structural calculations;
- autonomous safety certification;
- a general-purpose chatbot;
- native iOS or Android applications;
- arbitrary custom workflow builders.

## Product Success Criteria

The Golden demo starts when a project manager imports the canonical Ridge House
plan through the reviewed project-initialization flow. The confirmed source
must create First-floor blockwork, Electrical rough-in, First-floor plastering,
their dependency order, Cement Bags with 25 bags on hand, and a linked 100-bag
plastering requirement without manual project reconstruction.

The field statement against that imported project is:

> First-floor blockwork is complete. The electrician did not come today. We
> have 10 bags of cement left. Plastering starts tomorrow.

Without further prompting, the system must:

1. store the original update and any attachments;
2. mark the matched blockwork task complete;
3. create an electrical blocker tied to the relevant task;
4. identify the downstream task at risk;
5. update cement stock and calculate a shortage for plastering;
6. create a material request and pending approval;
7. update the daily report;
8. record each action in the activity timeline;
9. return a concise confirmation describing what happened and what needs the manager;
10. avoid duplicate mutations if the input event is delivered again.

The end-to-end demo is complete only when the import is reviewable and durable,
approving the request resumes the same workflow, and a later `DELIVERY_DELAYED`
event updates risk without a chat prompt.

The demo is not a release-quality exception. The same scenario must pass the production release controls for durable state, duplicate suppression, approval restart/resume, canonical material identity, evidence-based extraction, authorization, auditability, and API-backed UI state.

## Open Product Questions

These do not block foundation work but must be resolved before public beta:

- Which authentication providers, if any, follow the initial Email/Password public-beta flow?
- What monetary currency and approval threshold model applies per project?
- Is a manager allowed to override an extracted fact, and how is that correction fed into evals?
- What retention period applies to audio, photos, transcripts, and agent-run details?
