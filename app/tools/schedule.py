"""Typed dependency-aware schedule tools."""

from app.domain.activity import MutationContext
from app.domain.authorization import ProjectAccessContext
from app.domain.conversation import ScheduleChangeCommand
from app.services.conversation_schedule_operations import (
    ConversationScheduleService,
    ScheduleChangeResult,
    ScheduleProposal,
)


class ScheduleTools:
    def __init__(self, service: ConversationScheduleService, access: ProjectAccessContext) -> None:
        self._service = service
        self._access = access

    def propose_change(self, command: ScheduleChangeCommand) -> ScheduleProposal:
        return self._service.propose(self._access, command)

    def apply_change(
        self, command: ScheduleChangeCommand, context: MutationContext
    ) -> ScheduleChangeResult:
        return self._service.execute(self._access, command, context)


__all__ = ["ScheduleTools"]
