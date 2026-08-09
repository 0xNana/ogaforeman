from pathlib import Path

from scripts.run_clean_checkout_matrix import is_source_path_included


def test_clean_checkout_source_manifest_excludes_its_own_generated_artifact() -> None:
    assert not is_source_path_included(Path("artifacts/reliability/clean-checkout.json"))
    assert is_source_path_included(Path("app/main.py"))
