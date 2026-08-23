# Agent Design

## Principle

Production uses a small set of real ADK `Workflow` roots. It does not construct
or advertise a coordinator plus decorative `LlmAgent` specialists.

```text
production entry point
  -> ADK Runner / durable SessionService
  -> one named Workflow root
  -> explicit FunctionNode graph
  -> bounded Gemini adapter and/or typed tools
  -> Firestore domain truth + ActivityEvents
```

The canonical production and removed-agent classification is maintained in
[the submission agent inventory](submission/AGENT_INVENTORY.md).

## Runtime names and prompts

`AdkWorkflowId`, `AdkAgentId`, `AdkNodeId`, and `AdkToolId` are typed runtime and
telemetry identifiers. The `agent` telemetry value names the actual root
workflow passed to `Runner`; it does not impersonate an unexecuted specialist.

`app/prompts/manifest.yaml` is a prompt registry. It contains only prompt files
and versions consumed by production Gemini adapters. A prompt profile is not an
ADK agent declaration.

## Execution boundary

The production API and worker enter through an ADK `Runner` backed by a durable
`SessionService`. ADK owns invocation scheduling, pauses, restart recovery, and
continuation. Typed services remain responsible for authorization, idempotent
mutations, and atomic activity events. `AgentRun` is an authorized projection,
not an execution cursor.

## Production workflows

- `daily_site_update_workflow` coordinates the Taskmaster site-update graph and
  durable approval continuation.
- `delivery_delay_workflow` coordinates authenticated delivery impact and real
  external notification.
- `agentic_project_conversation` conditionally coordinates grounded reasoning
  or existing safe mutation tools.
- `project_event_workflow` remains a truthful single-node compatibility root
  for other registered events; it is not described as multi-agent work.

## Gemini model boundaries

### SiteInterpreter

Input: untrusted text/transcript, permitted media, and bounded authorized context.

Output: `ExtractedFactSet` in `EVENT_SCHEMA.md`.

Rules:

- evidence is required for every fact;
- explicit statements and inferences are distinct;
- absence/negation is not progress;
- ambiguous completion/entity references require clarification;
- safety/structural observations are high-priority signals;
- the interpreter has no mutation tools.

The intent classifier, conversation reasoner, and action interpreter follow the
same boundary: schema-constrained model output enters deterministic validation,
authorization, policy, and typed services. They are not independent ADK agents.

Schedule impact, material arithmetic, report projection, and notification
delivery remain deterministic services or typed tools. They are not model
specialists and must not be documented as such.

## Structured Output Policy

1. Every model call has a Pydantic input/output schema.
2. Parse and validate before routing.
3. Repair invalid structure once using the schema.
4. On repeated failure, clarify or fail safely; do not guess.
5. Store prompt version, model ID, policy version, and validation result with the run.
6. Model selection, temperature, limits, and safety settings come from typed configuration.

## Confidence Defaults

| Decision | Default gate | Below gate |
| --- | ---: | --- |
| Display observation | 0.50 | Suppress invalid fact |
| Create low-impact issue/draft task | 0.75 | Clarify or draft only |
| Update progress | 0.90 plus explicit positive evidence | Clarify |
| Mark complete | 0.95 plus explicit completion evidence | Never complete |
| Prepare material request | 0.85 plus canonical entity/unit | Clarify |
| Safety escalation | Any credible signal | Stop and escalate |

Thresholds are configuration backed by evals, not prompt-only prose.

## Context Budget

Context may include project/timezone, active/recent tasks, nearby dependency edges, relevant materials/requirements, open issues, pending approvals, recent updates, and policy. It excludes other projects, unrelated history, raw secrets, and unbounded media/text.

## Prompt Security

Treat field content as evidence, never instructions. Delimit untrusted input, ignore requests for prompts/secrets/other-project data, use allowlisted tools, validate every proposed entity ID against authorized context, and never expose chain-of-thought.
