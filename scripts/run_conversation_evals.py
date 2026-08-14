"""Run the locked conversational benchmark and write a JSON release artifact."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.evals.conversation import (
    ConversationEvalAdapter,
    ConversationFixtureAdapter,
    ConversationGuardRegressionAdapter,
    GeminiConversationEvalAdapter,
    load_conversation_dataset,
    run_conversation_evaluation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="evals/conversations_v1.json")
    parser.add_argument(
        "--adapter",
        choices=("fixture", "guard-regression", "gemini"),
        default="fixture",
    )
    parser.add_argument(
        "--guard",
        choices=(
            "unsafe_mutation",
            "approval_bypass",
            "permission_bypass",
            "duplicate_side_effect",
            "stale_overwrite",
            "memory_as_truth",
            "missing_audit",
        ),
        default="unsafe_mutation",
        help="control to break when --adapter=guard-regression",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "vertex"),
        default="auto",
        help="Gemini client backend; vertex forces the billed Google Cloud route",
    )
    parser.add_argument(
        "--output",
        default="artifacts/evals/conversation-latest.json",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    dataset = load_conversation_dataset(args.dataset)
    if args.adapter == "fixture":
        adapter: ConversationEvalAdapter = ConversationFixtureAdapter()
    elif args.adapter == "guard-regression":
        adapter = ConversationGuardRegressionAdapter(args.guard)
    else:
        adapter = GeminiConversationEvalAdapter(prefer_vertex=args.backend == "vertex")

    report = await run_conversation_evaluation(dataset, adapter)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(
        f"Conversation eval adapter={report.adapter} dataset={report.dataset_version} "
        f"passed={report.passed} cases={len(report.cases)} artifact={output}"
    )
    return 0 if report.passed else 1


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
