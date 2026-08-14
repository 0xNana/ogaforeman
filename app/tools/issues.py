"""Typed issue tools."""

from app.domain.activity import MutationContext
from app.domain.authorization import ProjectAccessContext
from app.services.issues import CreateIssueCommand, IssueChange, IssueService, UpdateIssueCommand


class IssueTools:
    def __init__(self, service: IssueService, access: ProjectAccessContext) -> None:
        self._service = service
        self._access = access

    def create_issue(self, command: CreateIssueCommand, context: MutationContext) -> IssueChange:
        return self._service.create_issue(self._access, command, context)

    def update_issue(self, command: UpdateIssueCommand, context: MutationContext) -> IssueChange:
        return self._service.update_issue(self._access, command, context)


__all__ = ["IssueTools"]
