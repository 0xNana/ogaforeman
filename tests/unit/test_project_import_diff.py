from app.services.project_import_diff import ProjectImportDiffService, DiffOperation
from app.domain.project_import import ProjectImportDraft, TaskDraft, ProjectDraft
from app.repositories.context import ProjectContext
from datetime import datetime, UTC


def test_project_import_diff_service_identifies_additions() -> None:
    service = ProjectImportDiffService()

    draft = ProjectImportDraft(
        id="import_123",
        project_id="prj_123",
        source_id="src_123",
        project=ProjectDraft(name="Test Project"),
        phases=[],
        tasks=[TaskDraft(temp_id="tmp_task_1", name="New Task", description="Test description")],
        dependencies=[],
        materials=[],
        material_requirements=[],
        milestones=[],
        warnings=[],
        conflicts=[],
        created_at=datetime.now(UTC),
    )

    context = ProjectContext(
        project_id="prj_123", active_tasks=[], materials=[], open_issues=[], pending_approvals=[]
    )

    diffs = service.compare(draft, context)
    assert len(diffs) == 1
    assert diffs[0].entity_type == "task"
    assert diffs[0].temp_id == "tmp_task_1"
    assert diffs[0].operation == DiffOperation.ADDED
