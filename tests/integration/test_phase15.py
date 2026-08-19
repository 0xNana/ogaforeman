from decimal import Decimal

import pytest

from app.domain.facts import ExtractedFactSet, MaterialQuantityFact
from app.domain.models import Material
from app.repositories.memory import InMemoryRepositoryStore
from app.worker import process_event_async
from app.config import Settings
from tests.integration.test_worker_site_update import FakeSiteInterpreter, _event, _seed, PROJECT_ID


@pytest.mark.asyncio
async def test_auto_create_material_during_operations() -> None:
    text = "60 pieces of building wire arrived."
    store = InMemoryRepositoryStore()
    _seed(store, raw_text=text)

    interpreter = FakeSiteInterpreter(
        responses={
            text: ExtractedFactSet(
                materials=[
                    MaterialQuantityFact(
                        material_name="Building Wire",
                        quantity=60.0,
                        unit="pieces",
                        evidence=text,
                        confidence="high",
                    )
                ]
            )
        }
    )

    await process_event_async(
        _event(text=text).model_dump_json().encode(),
        store=store,
        settings=Settings(_env_file=None),
        site_interpreter=interpreter,
    )

    materials = list(store.repository(Material).list(PROJECT_ID))
    wire = next((m for m in materials if m.name == "Building Wire"), None)
    assert wire is not None
    assert wire.available_quantity == Decimal("60")
    assert wire.unit == "pieces"
