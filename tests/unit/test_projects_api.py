from datetime import date

import pytest
from pydantic import ValidationError

from app.api.v1.projects import CreateProjectRequest
from app.domain.enums import ProjectStatus


def test_create_project_request_accepts_complete_project_details() -> None:
    request = CreateProjectRequest(
        name=" Ridge House ",
        location=" East Legon ",
        description=" Residential build ",
        timezone="Africa/Accra",
        start_date=date(2026, 9, 1),
        target_end_date=date(2027, 4, 30),
        status=ProjectStatus.PLANNING,
    )

    assert request.name == "Ridge House"
    assert request.location == "East Legon"
    assert request.description == "Residential build"
    assert request.status is ProjectStatus.PLANNING


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timezone", "Not/A_Timezone"),
        ("target_end_date", date(2026, 8, 31)),
    ],
)
def test_create_project_request_rejects_invalid_operational_fields(
    field: str, value: object
) -> None:
    payload: dict[str, object] = {
        "name": "Ridge House",
        "location": "East Legon",
        "timezone": "Africa/Accra",
        "start_date": date(2026, 9, 1),
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        CreateProjectRequest.model_validate(payload)
