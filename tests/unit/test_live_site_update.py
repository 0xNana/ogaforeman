import pytest

from app.config.settings import Settings
from app.domain.models import Material
from scripts.run_live_site_update import _assert_live_local_runtime
from scripts.seed_demo import seed_entities


def test_demo_seed_represents_pre_update_material_state() -> None:
    _project, _users, entities = seed_entities()
    cement = next(entity for entity in entities if isinstance(entity, Material))

    assert str(cement.available_quantity) == "25"


def test_live_rehearsal_rejects_fake_model_mode() -> None:
    settings = Settings(
        _env_file=None,
        firestore_emulator_host="127.0.0.1:8085",
        use_fake_model=True,
        gemini_api_key="developer-key",
        gemini_model_id="configured-model",
    )

    with pytest.raises(RuntimeError, match="USE_FAKE_MODEL=false"):
        _assert_live_local_runtime(settings)
