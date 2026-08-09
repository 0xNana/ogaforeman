"""Tests for entity resolution."""

from app.domain.models import Task, Material
from app.services.entity_resolution import resolve_task, resolve_material, MatchConfidence


def test_resolve_task_exact():
    task1 = Task(id="tsk_abc1", project_id="prj_abc1", title="Electrical Wiring")
    task2 = Task(id="tsk_abc2", project_id="prj_abc1", title="Plumbing")

    result = resolve_task("electrical wiring", [task1, task2])
    assert result.confidence == MatchConfidence.HIGH
    assert len(result.candidates) == 1
    assert result.candidates[0].id == "tsk_abc1"


def test_resolve_task_ambiguous():
    task1 = Task(id="tsk_abc1", project_id="prj_abc1", title="First Floor Blockwork")
    task2 = Task(id="tsk_abc2", project_id="prj_abc1", title="Second Floor Blockwork")

    result = resolve_task("blockwork", [task1, task2])
    assert result.confidence == MatchConfidence.AMBIGUOUS
    assert len(result.candidates) == 2


def test_resolve_task_unknown():
    task1 = Task(id="tsk_abc1", project_id="prj_abc1", title="Plastering")

    result = resolve_task("blockwork", [task1])
    assert result.confidence == MatchConfidence.UNKNOWN
    assert len(result.candidates) == 0


def test_resolve_material_exact_alias():
    mat1 = Material(
        id="mat_abc1",
        project_id="prj_abc1",
        name="Portland Cement",
        normalized_name="portland cement",
        aliases=["cement"],
        unit="bags",
    )
    mat2 = Material(
        id="mat_abc2",
        project_id="prj_abc1",
        name="Sand",
        normalized_name="sand",
        aliases=["sharp sand"],
        unit="tonnes",
    )

    result = resolve_material("cement", [mat1, mat2])
    assert result.confidence == MatchConfidence.HIGH
    assert len(result.candidates) == 1
    assert result.candidates[0].id == "mat_abc1"


def test_resolve_material_ambiguous():
    mat1 = Material(
        id="mat_abc1",
        project_id="prj_abc1",
        name="White Paint",
        normalized_name="white paint",
        aliases=["paint"],
        unit="litres",
    )
    mat2 = Material(
        id="mat_abc2",
        project_id="prj_abc1",
        name="Blue Paint",
        normalized_name="blue paint",
        aliases=["paint"],
        unit="litres",
    )

    result = resolve_material("paint", [mat1, mat2])
    assert result.confidence == MatchConfidence.AMBIGUOUS
    assert len(result.candidates) == 2


def test_resolve_material_unknown():
    mat1 = Material(
        id="mat_abc1",
        project_id="prj_abc1",
        name="Bricks",
        normalized_name="bricks",
        aliases=[],
        unit="pieces",
    )

    result = resolve_material("cement", [mat1])
    assert result.confidence == MatchConfidence.UNKNOWN
    assert len(result.candidates) == 0
