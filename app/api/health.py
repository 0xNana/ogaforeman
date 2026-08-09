"""Operational endpoints shared by the API and worker health servers."""

from __future__ import annotations

from google.cloud.storage import Client as StorageClient

from app.config.settings import RuntimeEnvironment, Settings
from app.infrastructure.firestore import create_firestore_client
from app.observability.health import HealthCheck, HealthRegistry, create_health_router
from app.observability.probes import configuration_probe, firestore_probe, storage_probe


router = create_health_router(registry=HealthRegistry())


def create_runtime_health_router(settings: Settings):
    """Build a readiness router with dependency checks for a deployed process."""

    registry = HealthRegistry((HealthCheck("configuration", configuration_probe(settings)),))
    if settings.oga_env in {RuntimeEnvironment.LOCAL, RuntimeEnvironment.TEST}:
        if settings.firestore_emulator_host:
            try:
                registry.add(
                    HealthCheck("firestore", firestore_probe(create_firestore_client(settings)))
                )
            except Exception as exc:
                error_name = type(exc).__name__
                registry.add(HealthCheck("firestore", lambda: (False, error_name)))
    else:
        try:
            registry.add(
                HealthCheck("firestore", firestore_probe(create_firestore_client(settings)))
            )
        except Exception as exc:
            error_name = type(exc).__name__
            registry.add(HealthCheck("firestore", lambda: (False, error_name)))
        if settings.media_bucket:
            try:
                storage = StorageClient(project=settings.google_cloud_project)
                registry.add(
                    HealthCheck(
                        "storage",
                        storage_probe(storage, settings.media_bucket),
                    )
                )
            except Exception as exc:
                error_name = type(exc).__name__
                registry.add(HealthCheck("storage", lambda: (False, error_name)))

    return create_health_router(registry=registry)


__all__ = ["create_runtime_health_router", "router"]
