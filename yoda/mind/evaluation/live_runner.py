"""CLI entry for on-demand live routing evaluation (TASK-021)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from yoda.api.llm_api import LLMApi
from yoda.mind.evaluation.data import LiveRunStatus
from yoda.mind.evaluation.live_core import LiveRoutingEvaluationCore
from yoda.mind.evaluation.live_evaluation import (
    DEFAULT_CORPUS_PATH,
    DEFAULT_REPORT_DIR,
    LiveRoutingEvaluation,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run on-demand live-model routing evaluation over the corpus.",
    )
    parser.add_argument("--case", dest="case_id", default=None)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS_PATH,
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("settings.json"),
    )
    return parser.parse_args(argv)


def _load_agent_settings(settings_path: Path) -> tuple[str, str]:
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    try:
        agent = payload["agent"]
        model_name = agent["model_name"]
        api_key = payload["llm"]["api_key"]
    except KeyError as exc:
        raise SystemExit(
            f"settings missing required key for live eval: {exc}",
        ) from exc
    if not model_name or not api_key:
        raise SystemExit("settings agent.model_name and llm.api_key are required")
    return model_name, api_key


async def _async_main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    model_name, api_key = _load_agent_settings(args.settings)
    evaluation = LiveRoutingEvaluation(
        llm_api=LLMApi(api_key=api_key),
        model_name=model_name,
    )
    report = await evaluation.run(
        args.corpus,
        case_id=args.case_id,
        report_dir=args.report_dir,
    )
    artifact = evaluation.last_artifact_path
    if artifact is None:
        raise SystemExit("live eval did not produce a report artifact")
    print(LiveRoutingEvaluationCore.format_console_summary(report, artifact))
    return 0 if report.status is not LiveRunStatus.FAILED else 1


def main(argv: list[str] | None = None) -> None:
    raise SystemExit(asyncio.run(_async_main(argv)))


if __name__ == "__main__":
    main(sys.argv[1:])
