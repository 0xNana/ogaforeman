# Production Agent Inventory

## Audit rule

An agent is `PRODUCTION_USED` only when production code passes that exact ADK
agent or workflow object to `google.adk.runners.Runner`. Constructing an
`LlmAgent`, exporting it, registering its prompt, or using its name in telemetry
does not qualify.

`PLANNED_NOT_USED` means there is an approved implementation plan but no current
production entry point. `DEAD` means there is no production execution path and
the declaration must not remain in the runtime architecture.

## Current production ADK roots

| Agent | Purpose | Production entry point | Runner/workflow | Tools | Status |
| --- | --- | --- | --- | --- | --- |
| `daily_site_update_workflow` | Coordinate persisted site evidence through context, Gemini extraction, canonical resolution, parallel progress/blocker/material analysis, policy, typed mutations, approval interruption, report projection, and completion. | `process_event_async` -> `SiteUpdateEventExecutor.execute` / `resume_approved` | `Runner`; `build_site_update_app`; root `Workflow(name="daily_site_update_workflow")` | `site_update_typed_tools`; ADK `RequestInput` approval boundary | `PRODUCTION_USED` |
| `delivery_delay_workflow` | Coordinate an authenticated delay through canonical request context, dependency impact, delayed-request mutation, risk, follow-up, external notification, and completion. | `process_event_async` -> `DeliveryDelayEventExecutor.execute` | `Runner`; root `Workflow(name="delivery_delay_workflow")` | `mark_material_request_delayed`, `create_issue`, `create_delivery_follow_up`, `send_delivery_notification` | `PRODUCTION_USED` |
| `agentic_project_conversation` | Route a project conversation through intent classification, authorized context, canonical entity resolution, grounded Gemini reasoning, or existing safe mutation tools. | `POST /api/v1/projects/{project_id}/conversations` -> `AdkConversationExecutor.execute_agentic` | `Runner`; root `Workflow(name="agentic_project_conversation")` | `conversation_typed_tools` through existing confirmation/approval policy | `PRODUCTION_USED` |
| `project_event_workflow` | Compatibility root for remaining registered non-site events and their approval continuation. It wraps one typed event-service node and is not presented as multi-agent orchestration. | `process_event_async` -> `AdkEventExecutor.execute` / `resume_approved` | `Runner`; root `Workflow(name="project_event_workflow")` | `TypedEventService`; ADK `RequestInput` approval boundary | `PRODUCTION_USED` |

There are no `PLANNED_NOT_USED` agents. New specialist agents require a concrete
production workflow need and must simplify or improve that workflow before they
can be declared.

## Production model adapters that are not agents

The prompt manifest is a prompt registry, not an agent registry. These profiles
are consumed by bounded Google Gen AI SDK adapters. None is constructed as an
ADK `LlmAgent`, registered as a sub-agent, or independently passed to `Runner`.

| Profile | Production consumer | Role | Status |
| --- | --- | --- | --- |
| `site_report` | `GeminiSiteInterpreter` inside the Daily Site Update workflow's `interpret_evidence` node | Schema-constrained site fact extraction | `PRODUCTION_USED` prompt |
| `intent_router` | `GeminiIntentClassifier` inside the Project Conversation workflow's `classify_intent` node | Typed intent classification | `PRODUCTION_USED` prompt |
| `agentic_conversation` | `GeminiConversationAgent` inside the Project Conversation workflow's reasoning node | Grounded answer generation over authorized context | `PRODUCTION_USED` prompt |
| `action_interpreter` | `GeminiActionInterpreter` before existing conversation mutation services | Typed semantic action interpretation | `PRODUCTION_USED` prompt |

## Removed declarations

| Agent declaration | Prior purpose/claim | Production entry point | Runner/workflow | Tools | Status |
| --- | --- | --- | --- | --- | --- |
| `oga_coordinator` `LlmAgent` | Claimed to route to four specialist sub-agents. | None | Never passed to `Runner`; constructed during package import only. | None | `DEAD` - removed |
| `site_report` `LlmAgent` export | Claimed specialist extraction. | None | Never passed to `Runner`; the real extraction path is `GeminiSiteInterpreter` inside a workflow node. | None | `DEAD` - removed |
| `planner` `LlmAgent` export | Claimed schedule-impact specialist. | None | Never passed to `Runner`; deterministic delivery-impact services run inside `delivery_delay_workflow`. | None | `DEAD` - removed |
| `materials` `LlmAgent` export | Claimed inventory/procurement specialist. | None | Never passed to `Runner`; deterministic material services and typed tools own this work. | None | `DEAD` - removed |
| `communicator` `LlmAgent` export | Claimed reports, briefs, and notification formatting. | None | Never passed to `Runner`; report and notification services own these outputs. | None | `DEAD` - removed |
| `ReporterAgent` singleton | Formatted a domain report and read communicator metadata. | None | Not an ADK agent and unused by production. | None | `DEAD` - removed |
| `intent_router`, `action_interpreter`, and `agentic_conversation` manifest agent records | Described direct Gemini prompt consumers as registered agents. | No agent entry point | No corresponding `LlmAgent`; retained only as accurately named prompt profiles. | None in manifest | `DEAD` as agent declarations - converted to prompts |

## Verification boundary

- `app/` contains no `LlmAgent` construction or exported agent singleton.
- Every production `Runner` root is one of the four workflows listed above.
- `AdkAgentId` values equal the real `AdkWorkflowId` root names used in stage telemetry.
- `app/prompts/manifest.yaml` has no tools, sub-agents, coordinator, planner,
  materials, or communicator declarations.
