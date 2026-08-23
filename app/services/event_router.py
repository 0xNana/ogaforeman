from app.domain.events import EventType, ProjectEvent
from app.agents.identifiers import AdkWorkflowId


def route_project_event(event: ProjectEvent) -> str:
    """
    Compatibility projection for callers that need a stable execution label.
    Approval continuation resolves its root from persisted state; all other
    labels name the actual ADK workflow selected by the worker.
    """
    return {
        EventType.SITE_UPDATE_RECEIVED: AdkWorkflowId.DAILY_SITE_UPDATE,
        EventType.TASK_COMPLETED: AdkWorkflowId.PROJECT_EVENT,
        EventType.MATERIAL_LOW: AdkWorkflowId.PROJECT_EVENT,
        EventType.MATERIAL_REQUESTED: AdkWorkflowId.PROJECT_EVENT,
        EventType.TASK_BLOCKED: AdkWorkflowId.PROJECT_EVENT,
        EventType.TASK_OVERDUE: AdkWorkflowId.PROJECT_EVENT,
        EventType.DELIVERY_DELAYED: AdkWorkflowId.DELIVERY_DELAY,
        EventType.DAILY_BRIEF_REQUESTED: AdkWorkflowId.PROJECT_EVENT,
        EventType.APPROVAL_GRANTED: "approval_continuation",
        EventType.APPROVAL_REJECTED: "approval_continuation",
    }[event.event_type]
