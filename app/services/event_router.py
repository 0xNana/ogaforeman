from app.agents.coordinator import coordinator
from app.domain.events import ProjectEvent


def route_project_event(event: ProjectEvent) -> str:
    """
    Entrypoint for all production events. Routes the event through OgaCoordinator.
    """
    result = coordinator.process_event(event)
    return result["route_decision"]
