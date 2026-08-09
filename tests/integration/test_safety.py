from app.services.safety import create_safety_issue
from app.services.issues import resolve_issue
from app.domain.models import IssueStatus


def test_safety_escalation_and_resolution():
    issue = create_safety_issue(
        project_id="proj_001", description="Dangerous exposed wiring", task_ids=["task_001"]
    )
    assert issue.status == IssueStatus.OPEN
    assert issue.description == "Dangerous exposed wiring"

    resolved = resolve_issue(issue, "Fixed wiring", "user_001")
    assert resolved.status == IssueStatus.RESOLVED
    assert resolved.resolved_at is not None
    assert resolved.owner_id == "user_001"
