# V1 Workflow Specifications

## Common Runtime Contract

```text
QUEUED -> RUNNING -> WAITING_FOR_APPROVAL
                  -> WAITING_FOR_CLARIFICATION
                  -> COMPLETED | FAILED
FAILED -> RETRYING -> RUNNING
FAILED -> DEAD_LETTERED
```

Each workflow persists `AgentRun` and a checkpoint after externally visible steps. Steps include event ID, trace ID, prompt/model/policy versions, attempt, and safe user-facing summary. Every step is idempotent.

## Project Initialization Import

```text
authorized project creation
  -> persist bounded source and exact create claim
  -> direct Gemini structured extraction using untrusted-source delimiters
  -> schema validation and deterministic normalization
  -> deterministic validation and additive-only conflict preflight
  -> persist review draft plus safe trace/registry diagnostics
  -> human confirm with expected version and idempotency claim
  -> rebuild and revalidate the immutable mutation plan transactionally
  -> atomically create canonical records, provenance, ledger, and activity
  -> mark import complete and refresh the operational project snapshot
```

The model owns only draft temporary references. Canonical IDs, persisted source
provenance, authorization, confirmation authority, and mutation execution remain
deterministic. Retry, refresh, and process restart resume the same persisted
source/import claim; exact replay cannot create another canonical mutation set.
Project initialization is an application ingestion pipeline. Its retries and
restart recovery use persisted `ProjectImport` state, never an ADK session.

## Daily Site Update

```text
claim event
  -> verify media and persist original input
  -> transcribe/prepare evidence
  -> load bounded project context
  -> SiteInterpreter structured facts
  -> validate and apply safety policy
  -> clarify if high-impact ambiguity exists
  -> fan out: progress | blocker -> dependency impact | materials
  -> join results and persist schedule risks
  -> apply typed safe mutations
  -> update source-linked daily report
  -> activity + durable AgentRun user response
```

Canonical acceptance input:

> First-floor blockwork is done. Electrician did not come. We have ten bags of cement left. Plastering is tomorrow.

Expected: blockwork complete; electrical blocker open; assigned source-linked
follow-up; plastering risk; cement shortage/request; approval where required; report
and activity updates; one mutation set after replay.

## Material Shortage

```text
MATERIAL_LOW/site fact
  -> resolve canonical material/unit
  -> read stock, reservations, upcoming requirements
  -> calculate shortage and needed-by
  -> deduplicate open request
  -> create request + approval
  -> checkpoint WAITING_FOR_APPROVAL
  -> approve: resume and claim supplier action
  -> reject: close request branch, notify, no supplier action
  -> delivery event: update request and downstream risk
```

All purchases require approval in V1, even when a cost threshold would otherwise allow automation.

## Blocker and Delay

```text
TASK_BLOCKED/TASK_OVERDUE/DELIVERY_DELAYED
  -> merge or create Issue
  -> resolve affected task IDs
  -> create/assign one source-linked follow-up task
  -> traverse dependency graph
  -> calculate projected impact and assumptions
  -> apply low-impact notifications/issue updates
  -> approval for major schedule/external changes
  -> safety stop for credible high/critical hazard
  -> monitor resolution
```

## Daily Brief

```text
DAILY_BRIEF_REQUESTED
  -> read reporting-window source state
  -> generate validated source-linked brief
  -> upsert one report projection per project/date
  -> notify recipients once
  -> activity + complete
```

## Clarification and Safety

Ambiguous entity, quantity, date, or completion evidence creates a persisted question and `WAITING_FOR_CLARIFICATION` state. A user answer is a new event referencing the original and resumes the checkpoint.

Credible safety/structural signal creates a high/critical issue, stops the normal branch, notifies a qualified role, and resumes only an explicitly approved safe action.

## Failure and Retry

- Retry transient model/cloud failures with bounded exponential backoff.
- Do not auto-retry authorization, schema, safety-stop, or invalid-state errors.
- Check external action claims before retrying side effects.
- Dead-letter poison events with an operator-visible run/error reference.
- Rebuild report projections from durable source entities; never erase source evidence to hide a projection failure.
