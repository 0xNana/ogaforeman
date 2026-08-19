import hashlib

import pytest

from app.domain.project_import import SourceType
from app.services.project_source_adapter import (
    StructuredTextInputError,
    StructuredTextProjectAdapter,
)


def test_adapter_normalizes_markdown_and_og_template_variation() -> None:
    source = StructuredTextProjectAdapter(name="plan.md").load(
        """# Residence\r\n\r\n## Activity: Excavation\r\nDate: 20 August 2026\r\n\r\n- Task: Foundation\r\nFinished by: 24 August 2026\r\nDependency: Excavation\r\n\r\nMaterials:\r\n- Cement: 100 bags\r\n"""
    )

    assert source.source_type is SourceType.MARKDOWN
    assert source.text == (
        "Residence\n\nTask: Excavation\nDue: 20 August 2026\n\n"
        "Task: Foundation\nDue: 24 August 2026\nDepends on: Excavation\n\n"
        "Materials:\nCement: 100 bags\n"
    )
    assert source.checksum == hashlib.sha256(source.text.encode()).hexdigest()


def test_adapter_preserves_unresolved_dates_and_does_not_invent_calendar_values() -> None:
    text = StructuredTextProjectAdapter().extract(
        "Task: Foundation\nDue: August\nDepends on: Excavation"
    )

    assert "Due: August" in text
    assert "2026" not in text


def test_adapter_rejects_empty_and_oversized_input() -> None:
    adapter = StructuredTextProjectAdapter()
    with pytest.raises(StructuredTextInputError):
        adapter.extract(" \n\t")
    with pytest.raises(StructuredTextInputError):
        adapter.extract("x" * (adapter._MAX_SOURCE_CHARS + 1))
