"""Tests for the fail-closed backed approval-resume release gate."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from unittest.mock import Mock

from scripts.run_adk_resume_gate import build_command, run_gate


def test_gate_refuses_to_skip_when_backing_service_endpoints_are_missing(
    capsys,
) -> None:
    runner = Mock()

    result = run_gate(environ={}, runner=runner)

    assert result == 2
    error = capsys.readouterr().err
    assert "FIRESTORE_EMULATOR_HOST" in error
    assert "STORAGE_EMULATOR_HOST" in error
    runner.assert_not_called()


def test_gate_runs_only_the_approved_restart_case_and_propagates_failure() -> None:
    runner = Mock(return_value=Mock(returncode=7))
    environ: Mapping[str, str] = {
        "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8080",
        "STORAGE_EMULATOR_HOST": "http://127.0.0.1:9199",
    }

    result = run_gate(environ=environ, runner=runner)

    assert result == 7
    runner.assert_called_once_with(build_command(Path.cwd()), cwd=Path.cwd(), check=False)
    command = runner.call_args.args[0]
    assert command[-1].endswith("[approved]")
    assert "-m" in command
    assert "backing_services" in command
