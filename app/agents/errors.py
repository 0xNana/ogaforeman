"""Typed, user-safe failures shared by agent runtime boundaries."""


class AgentDependencyUnavailableError(RuntimeError):
    """An external model or agent runtime dependency cannot serve the request."""

    code = "DEPENDENCY_UNAVAILABLE"


class AgentOutputInvalidError(ValueError):
    """An external model returned output that failed the typed contract."""

    code = "AGENT_OUTPUT_INVALID"


__all__ = ["AgentDependencyUnavailableError", "AgentOutputInvalidError"]
