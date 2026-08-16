# Native ADK runtime migration

The repository is pinned to `google-adk==2.6.2` by `uv.lock`. That release
provides the graph-based `google.adk.workflow.Workflow` API and the durable
`VertexAiSessionService`; the older `SequentialAgent` and `ParallelAgent`
primitives are deprecated in favor of `Workflow`.

The Daily Site Update worker now constructs a native ADK graph with explicit
`load_site_update`, `execute_site_update`, and `finalize_site_update` nodes in
`app/agents/adk_runtime.py`. ADK owns graph scheduling, event history, retry
configuration, and resumable session execution. The execute node calls the
application boundary, where authorization, typed tools, Firestore mutations,
approval policy, and ActivityEvents remain authoritative.

Session selection is explicit:

- local and test environments use the ADK SQLite `DatabaseSessionService`;
- preview, staging, and production require `VertexAiSessionService` and an
  `ADK_AGENT_ENGINE_ID`.

`InMemorySessionService` is not imported by the production worker. It remains
appropriate only for isolated ADK unit tests.

`AgentRun` remains a business-facing projection used by the existing API and
audit timeline. It is not used as the ADK session or graph checkpoint store.
Approval/clarification resumes reuse the same ADK session attempt; a failed
worker retry starts a fresh ADK attempt session while retaining the same
canonical business run ID, so a failed graph cannot be replayed as completed.

## Phase 16–19 evidence gates

- Phase 16 multimodal coverage uses the production worker path with deterministic
  Gemini and Storage boundaries; the real cloud voice/photo run remains a
  release gate requiring live model credentials and private media access.
- Phase 17 conversational site updates route through
  `ConversationSiteUpdateRouter` and `SiteUpdateIntakeService`, preserving the
  same event, coordinator, ADK workflow, typed mutation, approval, and audit
  path as direct intake.
- Phase 18 correlation is exposed by `AgentRun.adk_session_id`,
  `adk_invocation_id`, `adk_workflow_id`, and `trace_id`; ADK node events and
  domain ActivityEvents remain separate observable streams.
- Phase 19 is recorded in ADR-001 above. No private reasoning or raw media is
  exposed by the run projection.
