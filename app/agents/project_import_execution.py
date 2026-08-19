"""ADK Runner boundary for project-import draft extraction."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping

from google.adk.apps import App
from google.adk.runners import Runner
from google.genai import types

from app.agents.adk_runtime import (
    managed_session_service,
    session_app_name,
    sqlite_session_execution_guard,
)
from app.agents.project_import_extraction import ProjectImportExtractor, build_project_import_app
from app.config.settings import Settings
from app.domain.project_import import ProjectImportDraft
from app.repositories.interfaces import RepositoryStore


class AdkProjectImportExecutor:
    """Run extraction through the native ADK graph and return its typed draft."""

    def __init__(
        self,
        store: RepositoryStore,
        settings: Settings,
        extractor: ProjectImportExtractor,
    ) -> None:
        self._store = store
        self._settings = settings
        self._extractor = extractor

    async def extract(
        self,
        *,
        project_id: str,
        import_id: str,
        source_id: str,
        source_text: str,
    ) -> ProjectImportDraft:
        app_name = session_app_name(self._settings, self._store)
        app: App = build_project_import_app(
            f"{app_name}-project-import",
            source_text=source_text,
            project_id=project_id,
            import_id=import_id,
            source_id=source_id,
            extractor=self._extractor,
            timeout_seconds=self._settings.agent_workflow_timeout_seconds,
        )
        draft: ProjectImportDraft | None = None
        async with (
            managed_session_service(self._settings) as session_service,
            sqlite_session_execution_guard(self._settings),
            asyncio.timeout(self._settings.agent_workflow_timeout_seconds),
        ):
            runner = Runner(app=app, session_service=session_service, auto_create_session=True)
            async for event in runner.run_async(
                user_id=f"project:{project_id}",
                session_id=import_id,
                invocation_id=f"extract:{import_id}",
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text="Extract this project source for review.")],
                ),
            ):
                actions = event.actions
                if actions is None:
                    continue
                state_delta = actions.state_delta
                if not isinstance(state_delta, Mapping) or "draft" not in state_delta:
                    continue
                draft = ProjectImportDraft.model_validate_json(json.dumps(state_delta["draft"]))
        if draft is None:
            raise RuntimeError("ADK project import workflow completed without a draft")
        return draft


__all__ = ["AdkProjectImportExecutor"]
