"""Verify the documented release matrix in an isolated source-tree copy."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "reliability" / "clean-checkout.json"
EXCLUDED_FILES = {"artifacts/reliability/clean-checkout.json"}
COMMANDS: tuple[tuple[str, tuple[str, ...], str, int], ...] = (
    ("python_sync", ("uv", "sync", "--all-extras", "--locked"), ".", 0),
    ("ruff", (".venv/bin/ruff", "check", "."), ".", 0),
    ("format", (".venv/bin/ruff", "format", "--check", "."), ".", 0),
    ("mypy", (".venv/bin/mypy", "app"), ".", 0),
    ("backend", (".venv/bin/python", "-m", "pytest", "-q"), ".", 0),
    (
        "fixture_eval",
        (".venv/bin/python", "scripts/run_evals.py", "--adapter", "fixture"),
        ".",
        0,
    ),
    (
        "negative_eval",
        (
            ".venv/bin/python",
            "scripts/run_evals.py",
            "--adapter",
            "deliberate-regression",
            "--output",
            "artifacts/evals/deliberate-regression.json",
        ),
        ".",
        1,
    ),
    ("demo", (".venv/bin/python", "scripts/run_demo.py", "--runs", "3"), ".", 0),
    ("capacity", (".venv/bin/python", "scripts/run_capacity_baseline.py"), ".", 0),
    ("docs", (".venv/bin/python", "scripts/check_docs.py"), ".", 0),
    (
        "frontend_install",
        (
            "npm",
            "ci",
            "--prefer-offline",
            "--fetch-retries=5",
            "--fetch-retry-mintimeout=1000",
            "--fetch-retry-maxtimeout=10000",
        ),
        "frontend",
        0,
    ),
    ("frontend_lint", ("npm", "run", "lint"), "frontend", 0),
    ("frontend_types", ("npm", "run", "typecheck"), "frontend", 0),
    ("frontend_unit", ("npm", "test"), "frontend", 0),
    ("frontend_build", ("npm", "run", "build"), "frontend", 0),
    ("frontend_e2e", ("npm", "run", "test:e2e"), "frontend", 0),
)


def is_source_path_included(relative: Path) -> bool:
    return relative.as_posix() not in EXCLUDED_FILES


def source_files(root: Path = ROOT) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    files = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative = Path(os.fsdecode(raw_path))
        if not is_source_path_included(relative):
            continue
        source = root / relative
        if source.is_file() and not source.is_symlink():
            files.append(relative)
    return sorted(files, key=lambda path: path.as_posix())


def _copy_source(destination: Path, files: list[Path]) -> None:
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)


def _source_digest(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for relative in files:
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update((ROOT / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in (
        "FIRESTORE_EMULATOR_HOST",
        "GEMINI_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "MEDIA_BUCKET",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "UV_CACHE_DIR": "/tmp/oga-clean-uv-cache",
            "NPM_CONFIG_CACHE": "/tmp/oga-clean-npm-cache",
            "XDG_CONFIG_HOME": "/tmp/oga-clean-firebase",
            "OGA_ENV": "local",
            "DEMO_MODE": "true",
            "USE_FAKE_MODEL": "true",
        }
    )
    return environment


def _run_command(
    clean_root: Path,
    name: str,
    command: tuple[str, ...],
    working_directory: str,
    expected_exit: int,
) -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=clean_root / working_directory,
        env=_environment(),
        capture_output=True,
        text=True,
        timeout=600,
    )
    duration = round(time.monotonic() - started, 3)
    passed = result.returncode == expected_exit
    print(f"{name}: {'passed' if passed else 'failed'} ({duration:.3f}s)")
    if not passed:
        output = (result.stdout + "\n" + result.stderr).strip()
        print(output[-4_000:])
    return {
        "name": name,
        "command": list(command),
        "working_directory": working_directory,
        "expected_exit": expected_exit,
        "actual_exit": result.returncode,
        "duration_seconds": duration,
        "passed": passed,
    }


def main() -> None:
    files = source_files()
    with tempfile.TemporaryDirectory(prefix="oga-clean-checkout-", dir="/tmp") as directory:
        clean_root = Path(directory)
        _copy_source(clean_root, files)
        results = [
            _run_command(clean_root, name, command, working_directory, expected_exit)
            for name, command, working_directory, expected_exit in COMMANDS
        ]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_tree_sha256": _source_digest(files),
        "source_file_count": len(files),
        "passed": all(result["passed"] for result in results),
        "commands": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"artifact={OUTPUT.relative_to(ROOT)} passed={report['passed']}")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
