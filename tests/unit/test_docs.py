from scripts import check_docs
from scripts.check_docs import find_broken_links


def test_documentation_links_and_release_paths_exist() -> None:
    assert find_broken_links() == ()


def test_ignored_working_docs_are_excluded_from_public_validation(monkeypatch, tmp_path) -> None:
    (tmp_path / "README.md").write_text("# Public docs\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "internal-docs").mkdir()
    (tmp_path / "internal-docs" / "notes.md").write_text(
        "[private broken link](missing.md)\n", encoding="utf-8"
    )
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "plan.md").write_text(
        "[working broken link](missing.md)\n", encoding="utf-8"
    )
    monkeypatch.setattr(check_docs, "REQUIRED_RELEASE_PATHS", ())

    assert find_broken_links(tmp_path) == ()
