"""Run the live Gemini project-import release evaluation and write JSON evidence."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.agents.project_import_extraction import GeminiProjectImportExtractor
from app.config.settings import Settings
from app.evals.project_import import load_project_import_dataset, run_project_import_evaluation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="evals/project_import_v1.json")
    parser.add_argument(
        "--backend",
        choices=("auto", "vertex"),
        default="auto",
        help="Gemini client backend; vertex forces the billed Google Cloud route",
    )
    parser.add_argument("--output", default="artifacts/evals/project-import-live.json")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    settings = Settings(use_fake_model=False)
    if not settings.gemini_model_id:
        raise RuntimeError("GEMINI_MODEL_ID is required for the live project-import eval")
    dataset = load_project_import_dataset(args.dataset)
    report = await run_project_import_evaluation(
        dataset,
        GeminiProjectImportExtractor(settings, prefer_vertex=args.backend == "vertex"),
        model_id=settings.gemini_model_id,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        f"Project import eval model={report.model_id} dataset={report.dataset_version} "
        f"passed={report.passed} cases={len(report.cases)} artifact={output}"
    )
    return 0 if report.passed else 1


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
