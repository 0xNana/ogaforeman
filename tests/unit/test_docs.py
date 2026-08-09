from scripts.check_docs import find_broken_links


def test_documentation_links_and_release_paths_exist() -> None:
    assert find_broken_links() == ()
