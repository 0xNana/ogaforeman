from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.agents.interpreter import MediaEvidence
from app.prompts import PromptId, prompt_registry
from app.config.settings import Settings
from app.domain.conversation import (
    ContextDomain,
    ContextQuery,
    ConversationContext,
    ConversationalProjectContext,
    IntentType,
    MaterialOperation,
    ProjectContextItem,
)
from app.infrastructure.gemini import (
    GeminiActionInterpreter,
    GeminiConversationAgent,
    GeminiIntentClassifier,
    GeminiSiteInterpreter,
    create_gemini_client,
)
from app.services.conversation_action_composer import PurchaseActionInterpretation
from datetime import UTC, datetime


def test_local_api_key_uses_gemini_developer_api(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client_constructor = Mock(return_value=client)
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", client_constructor)
    settings = Settings(
        _env_file=None,
        use_fake_model=False,
        gemini_api_key="developer-key",
        conversation_proposal_signing_key="a" * 32,
        notification_provider="google_chat",
        google_chat_webhook_url=(
            "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=test-key&token=test-token"
        ),
        public_app_base_url="https://oga-staging.web.app",
        gemini_model_id="configured-model",
    )

    result = create_gemini_client(settings)

    assert result is client
    client_constructor.assert_called_once_with(api_key="developer-key")


def test_vertex_client_is_used_without_local_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client_constructor = Mock(return_value=client)
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", client_constructor)
    settings = Settings(
        _env_file=None,
        use_fake_model=False,
        google_cloud_project="oga-project",
        gemini_location="global",
        gemini_model_id="configured-model",
    )

    result = create_gemini_client(settings)

    assert result is client
    client_constructor.assert_called_once_with(
        vertexai=True,
        project="oga-project",
        location="global",
    )


def test_vertex_client_can_be_selected_explicitly_when_local_key_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_constructor = Mock(return_value=Mock())
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", client_constructor)
    settings = Settings(
        _env_file=None,
        use_fake_model=False,
        gemini_api_key="developer-key",
        google_cloud_project="oga-project",
        gemini_location="global",
        gemini_model_id="configured-model",
    )

    create_gemini_client(settings, prefer_vertex=True)

    client_constructor.assert_called_once_with(
        vertexai=True,
        project="oga-project",
        location="global",
    )


def test_site_interpreter_forwards_explicit_vertex_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_factory = Mock(return_value=Mock())
    monkeypatch.setattr("app.infrastructure.gemini.create_gemini_client", client_factory)
    settings = Settings(
        _env_file=None,
        use_fake_model=False,
        gemini_api_key="developer-key",
        google_cloud_project="oga-project",
        gemini_location="global",
        gemini_model_id="configured-model",
    )

    GeminiSiteInterpreter(settings, prefer_vertex=True)

    client_factory.assert_called_once_with(settings, prefer_vertex=True)


def test_deployed_runtime_uses_vertex_even_when_api_key_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_constructor = Mock(return_value=Mock())
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", client_constructor)
    settings = Settings(
        _env_file=None,
        oga_env="staging",
        app_git_sha="b134039daa3bc1528f9e869678dd6d59a4f9d1f9",
        app_build_time="2026-08-23T14:05:06Z",
        app_source_tree_dirty=False,
        demo_mode=False,
        use_fake_model=False,
        google_cloud_project="oga-staging",
        google_cloud_region="us-central1",
        firestore_database="(default)",
        media_bucket="oga-staging-media",
        storage_signing_service_account="oga-api@oga-staging.iam.gserviceaccount.com",
        pubsub_site_events_topic="oga-site-events",
        pubsub_dead_letter_topic="oga-dead-letter",
        pubsub_worker_subscription="oga-worker",
        gemini_model_id="configured-model",
        gemini_location="global",
        gemini_api_key="developer-key",
        conversation_proposal_signing_key="a" * 32,
        notification_provider="google_chat",
        google_chat_webhook_url=(
            "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=test-key&token=test-token"
        ),
        public_app_base_url="https://oga-staging.web.app",
        adk_agent_engine_id="agent-engine-staging",
        auth_issuer="https://securetoken.google.com/oga-staging",
        auth_audience="oga-staging",
        cors_allowed_origins=("https://oga-staging.web.app",),
    )

    create_gemini_client(settings)

    client_constructor.assert_called_once_with(
        vertexai=True,
        project="oga-staging",
        location="global",
    )


def test_live_gemini_rejects_fake_mode() -> None:
    settings = Settings(
        _env_file=None,
        use_fake_model=True,
        gemini_api_key="developer-key",
        gemini_model_id="configured-model",
    )

    with pytest.raises(RuntimeError, match="USE_FAKE_MODEL=false"):
        create_gemini_client(settings)


def test_interpreter_requires_configured_model() -> None:
    settings = Settings(
        _env_file=None,
        use_fake_model=False,
        gemini_api_key="developer-key",
    )

    with pytest.raises(RuntimeError, match="GEMINI_MODEL_ID"):
        GeminiSiteInterpreter(settings)


@pytest.mark.asyncio
async def test_gemini_intent_classifier_uses_typed_non_mutating_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text=(
                '{"intent":"site_update","confidence":0.96,'
                '"requested_action":null,"referenced_entities":[],'
                '"requires_project_context":true,"requires_mutation":true,'
                '"ambiguity":null,"reason_code":"multiple_site_facts"}'
            )
        )
    )
    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", Mock(return_value=client))
    classifier = GeminiIntentClassifier(
        Settings(
            _env_file=None,
            use_fake_model=False,
            gemini_api_key="developer-key",
            gemini_model_id="configured-model",
        )
    )

    result = await classifier.classify(
        "Blockwork is done and cement is low.",
        context=ConversationContext(has_active_project=True),
    )

    assert result.intent is IntentType.SITE_UPDATE
    call = generate_content.await_args.kwargs
    assert call["config"].response_schema is not None
    assert "has_active_project" in call["contents"][0].text
    assert "<user_message>" in call["contents"][0].text


@pytest.mark.asyncio
async def test_gemini_conversation_agent_generates_only_authorized_grounded_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text=(
                '{"text":"Blockwork is complete.",'
                '"cited_record_ids":["prj_gemini123"],"recommendation":null}'
            )
        )
    )
    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", Mock(return_value=client))
    agent = GeminiConversationAgent(
        Settings(
            _env_file=None,
            use_fake_model=False,
            gemini_api_key="developer-key",
            gemini_model_id="configured-model",
        )
    )
    context = ConversationalProjectContext(
        project_id="prj_gemini123",
        retrieved_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
        query=ContextQuery(domains=(ContextDomain.PROJECT,)),
        project=ProjectContextItem(
            id="prj_gemini123",
            name="Ridge House",
            location="Accra",
            timezone="Africa/Accra",
            status="active",
        ),
    )

    answer = await agent.respond(
        "What is our status?", intent=IntentType.PROJECT_QUERY, context=context
    )

    assert answer.text == "Blockwork is complete."
    assert answer.cited_record_ids == ("prj_gemini123",)
    call = generate_content.await_args.kwargs
    assert call["config"].response_schema is not None
    assert "Ridge House" in call["contents"][0].text


@pytest.mark.asyncio
async def test_gemini_action_interpreter_returns_typed_non_executing_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text=(
                '{"action":{"kind":"material","operation":"set_on_site",'
                '"material_reference":"cement","quantity":"100","unit":"bags",'
                '"reason":"Reported current stock count."}}'
            )
        )
    )
    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", Mock(return_value=client))
    interpreter = GeminiActionInterpreter(
        Settings(
            _env_file=None,
            use_fake_model=False,
            gemini_api_key="developer-key",
            gemini_model_id="configured-model",
        )
    )
    context = ConversationalProjectContext(
        project_id="prj_gemini123",
        retrieved_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
        query=ContextQuery(domains=(ContextDomain.MATERIALS,)),
    )

    action = await interpreter.interpret("we have 100 bags of cement", context=context)

    assert action.operation is MaterialOperation.SET_ON_SITE
    assert action.quantity == 100
    call = generate_content.await_args.kwargs
    assert call["config"].response_json_schema is not None
    assert "prj_gemini123" in call["contents"][0].text
    assert "<user_message>" in call["contents"][0].text


@pytest.mark.asyncio
async def test_gemini_action_interpreter_supports_relative_stock_adjustments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text=(
                '{"action":{"kind":"material","operation":"adjust_on_site",'
                '"material_reference":"cement","quantity_delta":"60","unit":"bags",'
                '"reason":"User requested an additional stock increment."}}'
            )
        )
    )
    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", Mock(return_value=client))
    interpreter = GeminiActionInterpreter(
        Settings(
            _env_file=None,
            use_fake_model=False,
            gemini_api_key="developer-key",
            gemini_model_id="configured-model",
        )
    )
    context = ConversationalProjectContext(
        project_id="prj_gemini123",
        retrieved_at=datetime(2026, 8, 15, 1, tzinfo=UTC),
        query=ContextQuery(domains=(ContextDomain.MATERIALS,)),
    )

    action = await interpreter.interpret("add additional 60 bags of cement", context=context)

    assert action.operation is MaterialOperation.ADJUST_ON_SITE
    assert action.quantity_delta == 60


@pytest.mark.parametrize(
    ("message", "response", "expected_operation"),
    [
        (
            "add 20 bags of cement to inventory",
            '{"action":{"kind":"material","operation":"adjust_on_site","material_reference":"cement","quantity_delta":"20","unit":"bags","reason":"Inventory increment."}}',
            MaterialOperation.ADJUST_ON_SITE,
        ),
        (
            "cement is at 20 bags now",
            '{"action":{"kind":"material","operation":"set_on_site","material_reference":"cement","quantity":"20","unit":"bags","reason":"Current stock count."}}',
            MaterialOperation.SET_ON_SITE,
        ),
        (
            "20 bags of cement arrived",
            '{"action":{"kind":"material","operation":"record_delivery","material_reference":"cement","material_request_reference":"cement request","quantity":"20","unit":"bags","reason":"Delivery received."}}',
            MaterialOperation.RECORD_DELIVERY,
        ),
        (
            "plastering needs another 20 bags of cement",
            '{"action":{"kind":"material","operation":"set_required","material_reference":"cement","quantity":"20","unit":"bags"}}',
            MaterialOperation.SET_REQUIRED,
        ),
    ],
)
@pytest.mark.asyncio
async def test_gemini_action_interpreter_preserves_material_operation_semantics(
    monkeypatch: pytest.MonkeyPatch,
    message: str,
    response: str,
    expected_operation: MaterialOperation,
) -> None:
    generate_content = AsyncMock(return_value=SimpleNamespace(text=response))
    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", Mock(return_value=client))
    interpreter = GeminiActionInterpreter(
        Settings(
            _env_file=None,
            use_fake_model=False,
            gemini_api_key="developer-key",
            gemini_model_id="configured-model",
        )
    )
    context = ConversationalProjectContext(
        project_id="prj_gemini123",
        retrieved_at=datetime(2026, 8, 15, 1, tzinfo=UTC),
        query=ContextQuery(domains=(ContextDomain.MATERIALS,)),
    )

    action = await interpreter.interpret(message, context=context)

    assert not isinstance(action, PurchaseActionInterpretation)
    assert action.operation is expected_operation


@pytest.mark.asyncio
async def test_gemini_action_interpreter_routes_purchase_to_approval_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text=(
                '{"action":{"kind":"purchase","material_reference":"cement",'
                '"quantity":"20","unit":"bags","reason":"Prepare a request."}}'
            )
        )
    )
    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", Mock(return_value=client))
    interpreter = GeminiActionInterpreter(
        Settings(
            _env_file=None,
            use_fake_model=False,
            gemini_api_key="developer-key",
            gemini_model_id="configured-model",
        )
    )
    context = ConversationalProjectContext(
        project_id="prj_gemini123",
        retrieved_at=datetime(2026, 8, 15, 1, tzinfo=UTC),
        query=ContextQuery(domains=(ContextDomain.MATERIALS,)),
    )

    action = await interpreter.interpret("prepare a request for 20 bags of cement", context=context)

    assert isinstance(action, PurchaseActionInterpretation)
    assert action.quantity == 20


@pytest.mark.asyncio
async def test_gemini_transcription_receives_inline_audio_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_content = AsyncMock(return_value=SimpleNamespace(text="Blockwork is complete."))
    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", Mock(return_value=client))
    interpreter = GeminiSiteInterpreter(
        Settings(
            _env_file=None,
            use_fake_model=False,
            gemini_api_key="developer-key",
            gemini_model_id="configured-model",
        )
    )
    audio = MediaEvidence(
        attachment_id="att_voice123",
        content_type="audio/webm",
        data=b"voice-bytes",
    )

    transcript = await interpreter.transcribe_audio(audio)

    assert transcript == "Blockwork is complete."
    call = generate_content.await_args.kwargs
    assert call["model"] == "configured-model"
    assert call["contents"][0].inline_data.data == b"voice-bytes"
    assert call["contents"][0].inline_data.mime_type == "audio/webm"


@pytest.mark.asyncio
async def test_gemini_fact_extraction_receives_image_bytes_and_project_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text='{"tasks":[],"materials":[],"issues":[],"next_focus":[],"safety_issues":[]}'
        )
    )
    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", Mock(return_value=client))
    interpreter = GeminiSiteInterpreter(
        Settings(
            _env_file=None,
            use_fake_model=False,
            gemini_api_key="developer-key",
            gemini_model_id="configured-model",
        )
    )
    image = MediaEvidence(
        attachment_id="att_photo123",
        content_type="image/png",
        data=b"photo-bytes",
    )

    result = await interpreter.extract_facts(
        "",
        images=(image,),
        project_context='{"tasks":[{"title":"Ground-floor blockwork"}]}',
    )

    assert result.tasks == []
    call = generate_content.await_args.kwargs
    prompt = call["contents"][0].text
    assert "Ground-floor blockwork" in prompt
    assert "A photo alone must not prove task completion" in prompt
    assert call["contents"][1].inline_data.data == b"photo-bytes"
    assert call["contents"][1].inline_data.mime_type == "image/png"


def test_site_report_prompt_locks_golden_multi_fact_extraction_contract() -> None:
    prompt = prompt_registry.get_prompt(PromptId.SITE_REPORT)

    assert "Extract every independent fact" in prompt
    assert "absent expected crew or trade" in prompt
    assert 'does not need to use the word "blocker"' in prompt
    assert "absolute on-hand stock" in prompt
    assert "canonical title" in prompt
    assert "material name" in prompt
    assert "canonical IDs" in prompt
