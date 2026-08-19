from app.domain.events import EventType, ProjectEvent


def route_project_event(event: ProjectEvent) -> str:
    """
    Compatibility projection for callers that need a stable workflow label.
    Execution is owned by the ADK Runner, not this label function.
    """
    return {
        EventType.SITE_UPDATE_RECEIVED: "site_report",
        EventType.TASK_COMPLETED: "daily_site_update",
        EventType.MATERIAL_LOW: "materials",
        EventType.MATERIAL_REQUESTED: "materials",
        EventType.TASK_BLOCKED: "planner",
        EventType.TASK_OVERDUE: "planner",
        EventType.DELIVERY_DELAYED: "planner",
        EventType.DAILY_BRIEF_REQUESTED: "communicator",
        EventType.APPROVAL_GRANTED: "approval_continuation",
        EventType.APPROVAL_REJECTED: "approval_continuation",
    }[event.event_type]
