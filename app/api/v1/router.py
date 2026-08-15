from fastapi import APIRouter
from app.api.v1 import (
    agent_runs,
    approvals,
    authentication,
    conversations,
    projects,
    resources,
    site_updates,
)

api_router = APIRouter()
api_router.include_router(authentication.router, prefix="/auth", tags=["authentication"])
api_router.include_router(
    conversations.user_router, prefix="/conversations", tags=["conversations"]
)
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(resources.router, prefix="/projects", tags=["project-resources"])
api_router.include_router(
    site_updates.router, prefix="/projects/{project_id}/site-updates", tags=["site-updates"]
)
api_router.include_router(
    approvals.router, prefix="/projects/{project_id}/approvals", tags=["approvals"]
)
api_router.include_router(
    agent_runs.router, prefix="/projects/{project_id}/agent-runs", tags=["agent-runs"]
)
api_router.include_router(
    conversations.router, prefix="/projects/{project_id}/conversations", tags=["conversations"]
)
