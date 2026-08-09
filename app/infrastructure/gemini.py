from google import genai
from google.genai import types

from app.agents.interpreter import SiteInterpreter
from app.agents.registry import registry
from app.config.settings import RuntimeEnvironment, Settings
from app.domain.facts import ExtractedFactSet


def create_gemini_client(settings: Settings) -> genai.Client:
    """Create a real Gemini client without falling back to a fake model."""

    if settings.use_fake_model:
        raise RuntimeError("Live Gemini requires USE_FAKE_MODEL=false")

    if (
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

    async def extract_facts(self, text: str) -> ExtractedFactSet:
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=f"{self._instruction}\n\nConstruction site update:\n{text}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExtractedFactSet,
                temperature=0.1,
            ),
        )
        if not response.text:
            return ExtractedFactSet()
        return ExtractedFactSet.model_validate_json(response.text)


__all__ = ["GeminiSiteInterpreter", "create_gemini_client"]
