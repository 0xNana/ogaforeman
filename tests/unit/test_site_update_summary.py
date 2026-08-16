from app.domain.facts import MaterialQuantityFact
from app.services.site_updates import _clarification_actions, _site_update_summary


def test_site_update_summary_is_user_facing_and_pluralized() -> None:
    assert _site_update_summary(0, 1, 0) == ("OG created 1 issue. The daily report is refreshed.")
    assert _site_update_summary(2, 0, 1) == (
        "OG updated 2 tasks and updated stock for 1 material. The daily report is refreshed."
    )


def test_site_update_summary_omits_internal_record_identifiers() -> None:
    summary = _site_update_summary(0, 0, 0)

    assert summary == "OG reviewed the update and refreshed the daily report."
    assert "rpt_" not in summary


def test_clarification_actions_explain_missing_material_quantity() -> None:
    actions = _clarification_actions(
        [
            MaterialQuantityFact(
                material_name="plasterboard",
                evidence="we have received the plasterboard deliveries",
                confidence="high",
            )
        ]
    )

    assert actions == [
        "I noted the plasterboard update, but need the quantity and unit to record it accurately."
    ]
