# Oga Foreman Agent Instructions

Before changing code, read:

1. `docs/PRODUCT.md`
2. `docs/ENGINEERING_SPEC.md`
3. `docs/PRODUCTION_READINESS.md`
4. the active section of `tasks/plan.md`
5. `tasks/todo-v1.md`

## Build Rules

- Implement only the active task and phase.
- Keep the four-workflow V1 scope locked.
- Gemini reasons; ADK workflows coordinate; typed tools mutate; Firestore is truth.
- Never use `_PROJECT_DB` in a production path.
- Every event consumer, workflow step, mutation, approval decision, notification, and external action must be idempotent or guarded by a persisted claim.
- Every mutation must atomically emit an `ActivityEvent`.
- Project authorization is enforced at API, repository, and tool boundaries.
- Never auto-approve purchases, external commitments, financial actions, task cancellation, major schedule changes, or safety-critical actions.
- Never let negated or ambiguous language mark a task complete.
- Use `datetime.now(UTC)` and timezone-aware schemas; do not add `datetime.utcnow()`.
- Do not derive identity from display names; use canonical IDs and explicit aliases.
- Keep prompt versions, agent names, tool names, and telemetry labels in a typed registry.
- Do not expose chain-of-thought or secrets in UI/logs.
- Do not add billing, subscriptions, credits, or unrelated construction-management scope.

## Verification

Run the task's verification commands before marking its checkbox complete. Use `uv sync --all-extras --locked` for Python and `npm ci` for the frontend. If a required tool is missing, install the documented development dependencies or report the exact environment blocker; do not claim tests passed.

At phase boundaries update `docs/STATUS.md`, `tasks/todo-v1.md`, and any affected contracts/ADRs.
