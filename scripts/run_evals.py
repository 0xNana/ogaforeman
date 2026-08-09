"""Run the locked Oga Foreman evaluation dataset and write a JSON artifact."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.evals.runner import (
    DeliberateRegressionAdapter,
    EvalAdapter,
    FixtureEvalAdapter,
    GeminiEvalAdapter,
    load_dataset,
    run_evaluation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="evals/site_updates_v1.json")
    parser.add_argument(
        "--adapter",
        choices=("fixture", "deliberate-regression", "gemini"),
        default="fixture",
    )
    parser.add_argument("--output", default="artifacts/evals/latest.json")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.dataset)
    if args.adapter == "fixture":
        adapter: EvalAdapter = FixtureEvalAdapter()
    elif args.adapter == "deliberate-regression":
        adapter = DeliberateRegressionAdapter()
    else:
        adapter = GeminiEvalAdapter()
    report = await run_evaluation(dataset, adapter)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(
        f"Eval adapter={report.adapter} dataset={report.dataset_version} "
        f"passed={report.passed} cases={len(report.cases)} artifact={output}"
    )
    return 0 if report.passed else 1


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
