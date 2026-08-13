from app.api.v1.projects import _project_member_names


class RuntimeWithoutMemberResolver:
    pass


def test_project_member_names_falls_back_for_compatible_runtime() -> None:
    assert _project_member_names(RuntimeWithoutMemberResolver(), "prj_ridge", "usr_manager") == {
        "usr_manager": "You"
    }


def test_project_member_names_rejects_malformed_optional_resolver_output() -> None:
    class MalformedRuntime:
        def project_member_names(self, project_id: str) -> dict[str, object]:
            assert project_id == "prj_ridge"
            return {"usr_manager": None}

    assert _project_member_names(MalformedRuntime(), "prj_ridge", "usr_manager") == {
        "usr_manager": "You"
    }
