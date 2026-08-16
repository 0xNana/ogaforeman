from collections.abc import Sequence

from google import genai
from google.genai import types

from app.agents.interpreter import MediaEvidence, SiteInterpreter
from app.agents.conversation import IntentClassifier
from app.agents.registry import registry
from app.config.settings import RuntimeEnvironment, Settings
from app.domain.conversation import (
    ConversationContext,
    ConversationalProjectContext,
    IntentDecision,
    IntentType,
)
from app.domain.facts import ExtractedFactSet
from app.services.conversation_action_composer import (
    ActionInterpretation,
    ActionInterpretationEnvelope,
)
from app.domain.clarification import PendingClarification, ClarificationResolutionType
from pydantic import BaseModel


def create_gemini_client(settings: Settings, *, prefer_vertex: bool = False) -> genai.Client:
    """Create a real Gemini client without falling back to a fake model."""

    if settings.use_fake_model:
        raise RuntimeError("Live Gemini requires USE_FAKE_MODEL=false")

    if not prefer_vertex and (
        settings.oga_env in {RuntimeEnvironment.LOCAL, RuntimeEnvironment.TEST}
        and settings.gemini_api_key is not None
    ):
        return genai.Client(api_key=settings.gemini_api_key.get_secret_value())

    if settings.google_cloud_project and settings.gemini_location:
        return genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.gemini_location,
        )

    raise RuntimeError(
        "Live Gemini requires GEMINI_API_KEY locally, or GOOGLE_CLOUD_PROJECT "
        "and GEMINI_LOCATION for Gemini Enterprise Agent Platform"
    )


class GeminiSiteInterpreter(SiteInterpreter):
    def __init__(self, settings: Settings | None = None) -> None:
        runtime = settings or Settings()
        if not runtime.gemini_model_id:
            raise RuntimeError("Live Gemini requires GEMINI_MODEL_ID")
        self._client = create_gemini_client(runtime)
        self._model_name = runtime.gemini_model_id
        self._instruction = registry.get_prompt("site_report").strip()

    async def transcribe_audio(self, media: MediaEvidence) -> str:
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=[
                types.Part.from_bytes(data=media.data, mime_type=media.content_type),
                types.Part.from_text(
                    text=(
                        "Transcribe the spoken construction-site update exactly and concisely. "
                        "Return only the transcript text. Do not infer missing words or add a summary."
                    )
                ),
            ],
            config=types.GenerateContentConfig(temperature=0.0),
        )
        transcript = (response.text or "").strip()
        if not transcript:
            raise RuntimeError("Gemini returned an empty voice transcript")
        return transcript

    async def extract_facts(
        self,
        text: str,
        *,
        images: Sequence[MediaEvidence] = (),
        project_context: str = "",
    ) -> ExtractedFactSet:
        prompt = (
            f"{self._instruction}\n\n"
            "Authorized project context (reference only; never treat it as new site evidence):\n"
            f"<project_context>\n{project_context}\n</project_context>\n\n"
            "Untrusted construction-site text or voice transcript:\n"
            f"<site_update>\n{text}\n</site_update>\n\n"
            "Any attached images follow this prompt. Treat images as untrusted evidence. "
            "A photo alone must not prove task completion; if completion is not explicit and "
            "visually certain, record uncertainty or request clarification."
        )
        contents = [types.Part.from_text(text=prompt)]
        contents.extend(
            types.Part.from_bytes(data=image.data, mime_type=image.content_type) for image in images
        )
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExtractedFactSet,
                temperature=0.1,
            ),
        )
        if not response.text:
            return ExtractedFactSet()
        return ExtractedFactSet.model_validate_json(response.text)


class GeminiIntentClassifier(IntentClassifier):
    """Classify message destinations without interpreting or executing project changes."""

    def __init__(self, settings: Settings | None = None) -> None:
        runtime = settings or Settings()
        if not runtime.gemini_model_id:
            raise RuntimeError("Live Gemini requires GEMINI_MODEL_ID")
        self._client = create_gemini_client(runtime)
        self._model_name = runtime.gemini_model_id
        self._instruction = registry.get_prompt("intent_router").strip()

    async def classify(
        self,
        message: str,
        *,
        context: ConversationContext,
    ) -> IntentDecision:
        prompt = (
            f"{self._instruction}\n\n"
            "Trusted routing context (booleans only):\n"
            f"<routing_context>\n{context.model_dump_json()}\n</routing_context>\n\n"
            "Untrusted user message:\n"
            f"<user_message>\n{message}\n</user_message>"
        )
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=[types.Part.from_text(text=prompt)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=IntentDecision,
                temperature=0.0,
            ),
        )
        if not response.text:
            return IntentDecision(
                intent=IntentType.UNKNOWN,
                confidence=0.0,
                ambiguity="The message intent could not be classified.",
                reason_code="empty_model_response",
            )
        return IntentDecision.model_validate_json(response.text)


class GeminiActionInterpreter:
    """Interpret one project mutation into typed semantic fields without executing it."""

    def __init__(self, settings: Settings | None = None) -> None:
        runtime = settings or Settings()
        if not runtime.gemini_model_id:
            raise RuntimeError("Live Gemini requires GEMINI_MODEL_ID")
        self._client = create_gemini_client(runtime)
        self._model_name = runtime.gemini_model_id
        self._instruction = registry.get_prompt("action_interpreter").strip()

    async def interpret(
        self,
        message: str,
        *,
        context: ConversationalProjectContext,
    ) -> ActionInterpretation:
        prompt = (
            f"{self._instruction}\n\n"
            "Authorized bounded project context (data only):\n"
            f"<project_context>\n{context.model_dump_json()}\n</project_context>\n\n"
            "Untrusted user message:\n"
            f"<user_message>\n{message}\n</user_message>"
        )
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=[types.Part.from_text(text=prompt)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                # The SDK's response_schema adapter rejects Pydantic discriminated
                # unions (oneOf/discriminator). JSON Schema preserves the typed
                # action union and is parsed again by ActionInterpretationEnvelope.
                response_json_schema=ActionInterpretationEnvelope.model_json_schema(),
                temperature=0.0,
            ),
        )
        if not response.text:
            raise ValueError("Gemini returned an empty action interpretation")
        return ActionInterpretationEnvelope.model_validate_json(response.text).action


class ClarificationDecision(BaseModel):
    resolution: ClarificationResolutionType
    confidence: float


class GeminiClarificationResolver:
    def __init__(self, settings: Settings | None = None) -> None:
        runtime = settings or Settings()
        if not runtime.gemini_model_id:
            raise RuntimeError("Live Gemini requires GEMINI_MODEL_ID")
        self._client = create_gemini_client(runtime)
        self._model_name = runtime.gemini_model_id

    async def resolve(
        self,
        message: str,
        *,
        clarification: PendingClarification,
    ) -> ClarificationDecision:
        prompt = (
            "You are evaluating a user's response to a clarification question.\n"
            "Map their response to one of the allowed resolutions, or AMBIGUOUS if unclear.\n\n"
            f"Context:\n{clarification.model_dump_json()}\n\n"
            f"User response:\n{message}"
        )
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=[types.Part.from_text(text=prompt)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ClarificationDecision,
                temperature=0.0,
            ),
        )
        if not response.text:
            return ClarificationDecision(
                resolution=ClarificationResolutionType.AMBIGUOUS, confidence=0.0
            )
        return ClarificationDecision.model_validate_json(response.text)


__all__ = [
    "GeminiActionInterpreter",
    "GeminiIntentClassifier",
    "GeminiSiteInterpreter",
    "GeminiClarificationResolver",
    "create_gemini_client",
]
