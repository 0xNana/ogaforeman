# Agent Design

## Principle

Use a coordinator and four narrow specialists. Agents return typed facts or proposals. ADK workflows control business steps, and deterministic tools enforce policies and mutations.

```text
OgaCoordinator
  +-- SiteInterpreter
  +-- ProjectPlanner
  +-- MaterialsSpecialist
  +-- Reporter
```

## Canonical Registry

Agent name, ADK name, prompt file/version, allowed tools, model configuration, and telemetry label live in one typed registry. Startup fails if a coordinator route references an absent/duplicate agent or prompt.

## OgaCoordinator

- validates project event and context;
- chooses registered workflows, not arbitrary names from input;
- invokes specialists and validates structured output;
- enforces safety and approval policy before tools;
- returns a safe action summary;
- never accesses Firestore directly or stores durable truth in its session.

The production API and Pub/Sub worker both enter through this coordinator. Direct workflow function calls are allowed only in tests or explicitly labeled local demos.

## SiteInterpreter

Input: untrusted text/transcript, permitted media, and bounded authorized context.

Output: `ExtractedFactSet` in `EVENT_SCHEMA.md`.

Rules:

- evidence is required for every fact;
- explicit statements and inferences are distinct;
- absence/negation is not progress;
- ambiguous completion/entity references require clarification;
- safety/structural observations are high-priority signals;
- the interpreter has no mutation tools.

## ProjectPlanner

Returns affected task IDs, dependency impact, projected delay and assumptions, mitigation proposals, review requirement, and confidence. It cannot silently alter committed dates or cancel work.

## MaterialsSpecialist

Uses canonical material IDs, stock ledger, task requirements, and project policy to calculate shortage and prepare a typed request. It cannot submit a supplier action without a resolved approval and claimed external action.

## Reporter

Builds source-linked daily reports, briefs, and concise user messages from durable facts. Unsupported claims are omitted rather than filled in.

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
