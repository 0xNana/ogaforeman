"""Typed identifiers shared by ADK graphs and telemetry."""

from enum import StrEnum


class AdkWorkflowId(StrEnum):
    DAILY_SITE_UPDATE = "daily_site_update_workflow"
    DELIVERY_DELAY = "delivery_delay_workflow"
    PROJECT_CONVERSATION = "agentic_project_conversation"
    PROJECT_EVENT = "project_event_workflow"


class AdkAgentId(StrEnum):
    DAILY_SITE_UPDATE = "daily_site_update_workflow"
    DELIVERY_DELAY = "delivery_delay_workflow"
    PROJECT_CONVERSATION = "agentic_project_conversation"
    PROJECT_EVENT = "project_event_workflow"


class AdkNodeId(StrEnum):
    RECEIVE_INPUT = "receive_input"
    PREPARE_MULTIMODAL_INPUT = "prepare_multimodal_input"
    RETRIEVE_AUTHORIZED_CONTEXT = "retrieve_authorized_context"
    INTERPRET_EVIDENCE = "interpret_evidence"
    RESOLVE_CANONICAL_ENTITIES = "resolve_canonical_entities"
    PROGRESS = "progress_node"
    BLOCKER = "blocker_node"
    MATERIAL = "material_node"
    MERGE_BRANCH_RESULTS = "merge_branch_results"
    MERGE_ACTIONS = "merge_actions"
    EVALUATE_POLICY = "evaluate_policy"
    EXECUTE_SITE_UPDATE = "execute_site_update"
    PROJECT_DAILY_LOG = "project_daily_log"
    EMIT_ACTIVITY = "emit_activity"
    FINALIZE_SITE_UPDATE = "finalize_site_update"
    RECEIVE_DELIVERY_DELAY = "receive_delivery_delay"
    RETRIEVE_REQUEST_CONTEXT = "retrieve_authorized_request_context"
    ASSESS_DELIVERY_IMPACT = "assess_material_schedule_impact"
    MARK_REQUEST_DELAYED = "mark_material_request_delayed_tool"
    CREATE_DELIVERY_RISK = "create_delivery_risk_tool"
    CREATE_DELIVERY_FOLLOW_UP = "create_delivery_follow_up_tool"
    DELIVER_DELIVERY_NOTIFICATION = "deliver_delivery_notification_tool"
    COMPLETE_DELIVERY_DELAY = "complete_delivery_delay"
    CLASSIFY_INTENT = "classify_intent"
    REASON_OVER_CONTEXT = "reason_over_authorized_context"
    INVOKE_CONVERSATION_TOOLS = "invoke_conversation_typed_tools"


class AdkToolId(StrEnum):
    SITE_UPDATE_TOOLS = "site_update_typed_tools"
    MARK_MATERIAL_REQUEST_DELAYED = "mark_material_request_delayed"
    CREATE_ISSUE = "create_issue"
    CREATE_DELIVERY_FOLLOW_UP = "create_delivery_follow_up"
    SEND_DELIVERY_NOTIFICATION = "send_delivery_notification"
    CONVERSATION_TOOLS = "conversation_typed_tools"


__all__ = ["AdkAgentId", "AdkNodeId", "AdkToolId", "AdkWorkflowId"]
