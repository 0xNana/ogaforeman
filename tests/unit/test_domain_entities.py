from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    ApprovalActionType,
    ApprovalStatus,
    AttachmentUploadStatus,
    IssueDetectedBy,
    IssueStatus,
    IssueType,
    MaterialRequestStatus,
    MemberRole,
    MemberStatus,
    ProcessedEventStatus,
    ProcessingStatus,
    ReportStatus,
    Severity,
    SiteUpdateInputType,
    UserStatus,
    WorkflowName,
)
from app.domain.models import (
    ActivityEvent,
    AgentRun,
    Approval,
    Attachment,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    ProcessedEvent,
    ProjectMember,
    ReportFact,
    SiteUpdate,
    User,
)
from app.domain.policies import (
    InvalidTransitionError,
    ensure_approval_transition,
    ensure_material_request_transition,
)


NOW = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)


def test_user_and_project_member_validate_identity_and_roles() -> None:
    user = User(
        id="usr_foreman",
        identity_subject="firebase-foreman",
        display_name="Site Foreman",
        email="foreman@example.com",
        status=UserStatus.ACTIVE,
    )
    member = ProjectMember(
        project_id="prj_ridge",
        user_id=user.id,
        role=MemberRole.FOREMAN,
        status=MemberStatus.ACTIVE,
    )

    assert member.user_id == user.id

    with pytest.raises(ValidationError):
        User(
            id="usr_invalid",
            identity_subject="firebase-invalid",
            display_name="User",
            email="not-an-email",
        )


def test_site_update_requires_real_input_and_aware_times() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        SiteUpdate(
            id="sup_update001",
            project_id="prj_ridge",
            submitted_by="usr_foreman",
            input_type=SiteUpdateInputType.TEXT,
            client_event_id="client-update-1",
        )

    update = SiteUpdate(
        id="sup_update001",
        project_id="prj_ridge",
        submitted_by="usr_foreman",
        input_type=SiteUpdateInputType.TEXT,
        raw_text="Blockwork is complete.",
        client_event_id="client-update-1",
        processing_status=ProcessingStatus.RECEIVED,
    )

    assert update.submitted_at.tzinfo is not None


def test_site_update_tracks_persisted_transcription_only_for_linked_audio() -> None:
    update = SiteUpdate(
        id="sup_update001",
        project_id="prj_ridge",
        submitted_by="usr_foreman",
        input_type=SiteUpdateInputType.VOICE,
        transcript="Electrician did not come.",
        attachment_ids=["att_audio001"],
        transcribed_attachment_ids=["att_audio001"],
        client_event_id="client-update-1",
    )

    assert update.transcript == "Electrician did not come."

    with pytest.raises(ValidationError, match="belong to the site update"):
        SiteUpdate(
            **{
                **update.model_dump(),
                "transcribed_attachment_ids": ["att_audio002"],
            }
        )

    with pytest.raises(ValidationError, match="transcript is required"):
        SiteUpdate(**{**update.model_dump(), "transcript": None})


def test_site_update_terminal_processing_state_requires_ordered_processed_time() -> None:
    with pytest.raises(ValidationError, match="processed_at"):
        SiteUpdate(
            id="sup_update001",
            project_id="prj_ridge",
            submitted_by="usr_foreman",
            input_type=SiteUpdateInputType.TEXT,
            raw_text="Blockwork is complete.",
            client_event_id="client-update-1",
            processing_status=ProcessingStatus.COMPLETED,
        )

    with pytest.raises(ValidationError, match="processed_at"):
        SiteUpdate(
            id="sup_update001",
            project_id="prj_ridge",
            submitted_by="usr_foreman",
            input_type=SiteUpdateInputType.TEXT,
            raw_text="Blockwork is complete.",
            client_event_id="client-update-1",
            processing_status=ProcessingStatus.COMPLETED,
            submitted_at=NOW,
            processed_at=datetime(2026, 8, 7, 9, 59, tzinfo=UTC),
        )


def test_attachment_validates_size_checksum_and_content_type() -> None:
    attachment = Attachment(
        id="att_photo001",
        project_id="prj_ridge",
        site_update_id="sup_update001",
        object_path="projects/prj_ridge/attachments/att_photo001.jpg",
        content_type="image/jpeg",
        byte_size=1_024,
        sha256="a" * 64,
        upload_status=AttachmentUploadStatus.VERIFIED,
    )

    assert attachment.byte_size == 1_024

    with pytest.raises(ValidationError):
        Attachment(**{**attachment.model_dump(), "sha256": "not-a-checksum"})


def test_material_rejects_negative_or_over_reserved_stock() -> None:
    with pytest.raises(ValidationError):
        Material(
            id="mat_cement",
            project_id="prj_ridge",
            name="Cement",
            normalized_name="cement",
            unit="bags",
            available_quantity=Decimal("-1"),
        )

    with pytest.raises(ValidationError, match="reserved_quantity"):
        Material(
            id="mat_cement",
            project_id="prj_ridge",
            name="Cement",
            normalized_name="cement",
            unit="bags",
            available_quantity=Decimal("10"),
            reserved_quantity=Decimal("11"),
        )


def test_material_request_requires_positive_quantity_and_approval_link() -> None:
    with pytest.raises(ValidationError):
        MaterialRequest(
            id="mrq_cement001",
            project_id="prj_ridge",
            material_id="mat_cement",
            quantity=Decimal("0"),
            unit="bags",
            reason="Plastering",
            source_event_id="evt_update001",
        )

    with pytest.raises(ValidationError, match="approval_id"):
        MaterialRequest(
            id="mrq_cement001",
            project_id="prj_ridge",
            material_id="mat_cement",
            quantity=Decimal("30"),
            unit="bags",
            reason="Plastering",
            source_event_id="evt_update001",
            status=MaterialRequestStatus.AWAITING_APPROVAL,
        )


def test_approval_terminal_state_requires_resolution_metadata() -> None:
    with pytest.raises(ValidationError, match="resolved_at"):
        Approval(
            id="apr_cement001",
            project_id="prj_ridge",
            action_type=ApprovalActionType.PURCHASE,
            proposed_action={"material_request_id": "mrq_cement001"},
            reason="Cement shortage",
            status=ApprovalStatus.APPROVED,
            requested_by="system",
            resolved_by="usr_manager",
        )

    with pytest.raises(ValidationError, match="must be empty"):
        Approval(
            id="apr_cement001",
            project_id="prj_ridge",
            action_type=ApprovalActionType.PURCHASE,
            proposed_action={"material_request_id": "mrq_cement001"},
            reason="Cement shortage",
            status=ApprovalStatus.PENDING,
            requested_by="system",
            resolved_at=NOW,
            resolved_by="usr_manager",
        )

    with pytest.raises(ValidationError, match="requested_at"):
        Approval(
            id="apr_cement001",
            project_id="prj_ridge",
            action_type=ApprovalActionType.PURCHASE,
            proposed_action={"material_request_id": "mrq_cement001"},
            reason="Cement shortage",
            status=ApprovalStatus.REJECTED,
            requested_by="system",
            requested_at=NOW,
            resolved_at=datetime(2026, 8, 7, 9, 59, tzinfo=UTC),
            resolved_by="usr_manager",
        )


def test_issue_and_report_preserve_source_references() -> None:
    issue = Issue(
        id="iss_electric001",
        project_id="prj_ridge",
        type=IssueType.BLOCKER,
        severity=Severity.HIGH,
        description="Electrician absent",
        evidence_refs=["sup_update001:fact_2"],
        task_ids=["tsk_electrical"],
        status=IssueStatus.OPEN,
        detected_by=IssueDetectedBy.SITE_UPDATE,
    )
    report = DailyReport(
        id="rpt_20260807",
        project_id="prj_ridge",
        report_date=date(2026, 8, 7),
        summary="Blockwork completed; electrical work blocked.",
        active_blockers=[
            ReportFact(summary=issue.description, source_refs=[issue.id, "sup_update001"])
        ],
        source_update_ids=["sup_update001"],
        status=ReportStatus.DRAFT,
    )

    assert report.active_blockers[0].source_refs == [issue.id, "sup_update001"]


def test_issue_resolution_timestamp_matches_terminal_status() -> None:
    with pytest.raises(ValidationError, match="resolved_at"):
        Issue(
            id="iss_electric001",
            project_id="prj_ridge",
            type=IssueType.BLOCKER,
            severity=Severity.HIGH,
            description="Electrician absent",
            status=IssueStatus.RESOLVED,
            detected_by=IssueDetectedBy.SITE_UPDATE,
        )

    with pytest.raises(ValidationError, match="resolved_at"):
        Issue(
            id="iss_electric001",
            project_id="prj_ridge",
            type=IssueType.BLOCKER,
            severity=Severity.HIGH,
            description="Electrician absent",
            status=IssueStatus.OPEN,
            detected_by=IssueDetectedBy.SITE_UPDATE,
            resolved_at=NOW,
        )


def test_agent_run_and_processed_event_enforce_terminal_metadata() -> None:
    with pytest.raises(ValidationError, match="completed_at"):
        AgentRun(
            id="run_update001",
            project_id="prj_ridge",
            trigger_event_id="evt_update001",
            workflow=WorkflowName.DAILY_SITE_UPDATE,
            status=AgentRunStatus.COMPLETED,
            trace_id="trace-update-1",
        )

    with pytest.raises(ValidationError, match="error_code"):
        AgentRun(
            id="run_update001",
            project_id="prj_ridge",
            trigger_event_id="evt_update001",
            workflow=WorkflowName.DAILY_SITE_UPDATE,
            status=AgentRunStatus.FAILED,
            trace_id="trace-update-1",
            started_at=NOW,
            completed_at=NOW,
        )

    with pytest.raises(ValidationError, match="completed_at"):
        ProcessedEvent(
            id="site-update:sup_update001:v1",
            project_id="prj_ridge",
            event_id="evt_update001",
            event_type="SITE_UPDATE_RECEIVED",
            event_fingerprint="a" * 64,
            status=ProcessedEventStatus.COMPLETED,
        )

    with pytest.raises(ValidationError, match="completed_at"):
        AgentRun(
            id="run_update001",
            project_id="prj_ridge",
            trigger_event_id="evt_update001",
            workflow=WorkflowName.DAILY_SITE_UPDATE,
            status=AgentRunStatus.RUNNING,
            trace_id="trace-update-1",
            completed_at=NOW,
        )

    with pytest.raises(ValidationError, match="first_seen_at"):
        ProcessedEvent(
            id="site-update:sup_update001:v1",
            project_id="prj_ridge",
            event_id="evt_update001",
            event_type="SITE_UPDATE_RECEIVED",
            event_fingerprint="a" * 64,
            status=ProcessedEventStatus.COMPLETED,
            first_seen_at=NOW,
            completed_at=datetime(2026, 8, 7, 9, 59, tzinfo=UTC),
        )


def test_activity_requires_actor_identity_for_user_or_agent() -> None:
    with pytest.raises(ValidationError, match="actor_id"):
        ActivityEvent(
            id="act_update001",
            project_id="prj_ridge",
            actor_type=ActorType.USER,
            action="task.completed",
            entity_type="task",
            entity_id="tsk_blockwork",
            summary="Blockwork completed",
        )


def test_terminal_transition_policies_are_one_way() -> None:
    ensure_approval_transition(ApprovalStatus.PENDING, ApprovalStatus.APPROVED)
    ensure_material_request_transition(
        MaterialRequestStatus.AWAITING_APPROVAL,
        MaterialRequestStatus.APPROVED,
    )

    with pytest.raises(InvalidTransitionError):
        ensure_approval_transition(ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)

    with pytest.raises(InvalidTransitionError):
        ensure_material_request_transition(
            MaterialRequestStatus.REJECTED,
            MaterialRequestStatus.SUBMITTED,
        )
