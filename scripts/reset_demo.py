from __future__ import annotations

from google.cloud import firestore

from app.config.settings import Settings
from app.infrastructure.firestore import assert_demo_environment, create_firestore_client
from scripts.seed_demo import DEMO_PROJECT_ID, SeedResult, seed_demo


def reset_demo(
    client: firestore.Client,
    *,
    settings: Settings | None = None,
) -> SeedResult:
    assert_demo_environment(settings)
    client.recursive_delete(client.document("projects", DEMO_PROJECT_ID))
    return seed_demo(client, settings=settings)


def main() -> None:
    settings = Settings()
    client = create_firestore_client(settings)
    result = reset_demo(client, settings=settings)
    print(f"Reset and reseeded {result.project_id}.")


if __name__ == "__main__":
    main()
