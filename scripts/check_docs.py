"""Validate public Markdown links and release-command file references."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
REQUIRED_RELEASE_PATHS = (
    "scripts/run_demo.py",
    "scripts/run_evals.py",
    "scripts/run_golden_evals.py",
    "scripts/run_adk_resume_gate.py",
    "scripts/verify_deployment_provenance.py",
    "scripts/run_capacity_baseline.py",
    "scripts/smoke_observability.py",
    "scripts/verify_backups.py",
    "scripts/rebuild_projections.py",
    "infra/deploy.sh",
    "infra/rollback.sh",
    "infra/monitoring/apply.sh",
    ".github/workflows/ci.yml",
    "docs/submission/ARCHITECTURE.md",
    "docs/submission/architecture-diagram.svg",
    "docs/submission/AGENT_INVENTORY.md",
    "docs/submission/DEVPOST.md",
    "docs/submission/TESTING.md",
    "docs/submission/ridge-house-plan.md",
)


def find_broken_links(root: Path = ROOT) -> tuple[str, ...]:
    markdown_files = [root / "README.md"] + sorted((root / "docs").rglob("*.md"))
    broken: list[str] = []
    for document in markdown_files:
        source = document.read_text(encoding="utf-8")
        for raw_target in LINK_RE.findall(source):
            target = _link_target(raw_target)
            if target is None:
                continue
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                broken.append(f"{document.relative_to(root)} -> {target}")
    for relative in REQUIRED_RELEASE_PATHS:
        if not (root / relative).exists():
            broken.append(f"required release path is missing: {relative}")
    return tuple(sorted(set(broken)))


def main() -> int:
    broken = find_broken_links()
    if broken:
        for item in broken:
            print(item)
        return 1
    print("Documentation links and release-command paths are valid.")
    return 0


def _link_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    target = unquote(target.split("#", maxsplit=1)[0])
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    return target


if __name__ == "__main__":
    raise SystemExit(main())
