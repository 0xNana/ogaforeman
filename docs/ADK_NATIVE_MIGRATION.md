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
