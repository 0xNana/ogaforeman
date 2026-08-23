"""Run the backed approval-resume gate, failing if its dependencies are absent."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENDPOINTS = ("FIRESTORE_EMULATOR_HOST", "STORAGE_EMULATOR_HOST")
APPROVED_RESTART_TEST = (
    "tests/integration/test_worker_site_update_firestore.py::"
    "test_voice_approval_continuation_survives_restart_and_executes_once[approved]"
)
CommandRunner = Callable[..., subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]]


def build_command(root: Path = ROOT) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        "backing_services",
        str(root / APPROVED_RESTART_TEST),
    ]


def run_gate(
    *,
    environ: Mapping[str, str] = os.environ,
    runner: CommandRunner = subprocess.run,
    root: Path = ROOT,
) -> int:
    missing = [name for name in REQUIRED_ENDPOINTS if not environ.get(name)]
    if missing:
        print(
            "Approval-resume gate refused to run; missing required endpoint(s): "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    completed = runner(build_command(root), cwd=root, check=False)
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print("This gate does not accept arguments.", file=sys.stderr)
        return 2
    return run_gate()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
