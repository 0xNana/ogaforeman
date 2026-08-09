from app.agents.registry import registry
from app.domain.events import EventType, ProjectEvent


class OgaCoordinator:
    def __init__(self) -> None:
        self.config = registry.get_agent_config("oga_coordinator")

    def route_event(self, event: ProjectEvent) -> str:
        routes = {
            EventType.SITE_UPDATE_RECEIVED: "site_report",
            EventType.TASK_COMPLETED: "site_report",
            EventType.MATERIAL_LOW: "materials",
            EventType.MATERIAL_REQUESTED: "materials",
            EventType.DELIVERY_DELAYED: "materials",
            EventType.APPROVAL_GRANTED: "materials",
            EventType.APPROVAL_REJECTED: "materials",
            EventType.TASK_BLOCKED: "planner",
            EventType.TASK_OVERDUE: "planner",
            EventType.DAILY_BRIEF_REQUESTED: "communicator",
        }
        route_name = routes[event.event_type]
        registry.get_agent_config(route_name)
        if route_name not in self.config.sub_agents:
            raise ValueError(f"Agent {route_name} is not a valid sub-agent of coordinator")
        return route_name

    def process_event(self, event: ProjectEvent) -> dict[str, str]:
        route_name = self.route_event(event)
        return {"route_decision": route_name, "event_id": event.event_id}


coordinator = OgaCoordinator()
