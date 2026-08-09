from app.domain.models import Issue, IssueType, Severity, IssueStatus, IssueDetectedBy
import uuid


def create_safety_issue(project_id: str, description: str, task_ids: list[str]) -> Issue:
    issue_id = f"issue_{uuid.uuid4().hex[:12]}"
    return Issue(
        id=issue_id,
        project_id=project_id,
        type=IssueType.SAFETY,
        severity=Severity.CRITICAL,
        description=description,
        task_ids=task_ids,
        status=IssueStatus.OPEN,
        detected_by=IssueDetectedBy.SITE_UPDATE,
    )
