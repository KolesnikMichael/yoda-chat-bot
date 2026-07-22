"""Live routing evaluation eligibility and report aggregation (TASK-021)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from yoda.mind.evaluation.data import (
    STAGE_ORDER,
    IntentExpectation,
    LiveCaseExclusion,
    LiveEvalReport,
    LiveExclusionReason,
    LiveRunStatus,
    LiveStageMetrics,
    OperationalErrorCategory,
    PlanningExpectation,
    PromptIdentity,
    RoutingCase,
    RoutingCaseResult,
    SelectionExpectation,
    StageName,
    StageStatus,
)


class LiveRoutingEvaluationCore:
    @staticmethod
    def live_eligibility(case: RoutingCase) -> LiveCaseExclusion | None:
        for turn in case.turns:
            intent = turn.expected.intent
            if (
                isinstance(intent, IntentExpectation)
                and intent.route == "rejected_fallback_chat"
            ):
                return LiveCaseExclusion(
                    case_id=case.id,
                    reason=LiveExclusionReason.FORCED_MALFORMED_INTENT,
                )
            selection = turn.expected.selection
            if isinstance(selection, SelectionExpectation):
                if selection.mode == "protocol_exhausted":
                    return LiveCaseExclusion(
                        case_id=case.id,
                        reason=LiveExclusionReason.FORCED_PROTOCOL_EXHAUSTION,
                    )
                if selection.recovery in ("corrected", "exhausted"):
                    return LiveCaseExclusion(
                        case_id=case.id,
                        reason=LiveExclusionReason.FORCED_SELECTION_RECOVERY,
                    )
            planning = turn.expected.planning
            if (
                isinstance(planning, PlanningExpectation)
                and planning.recovery in ("corrected", "exhausted")
            ):
                return LiveCaseExclusion(
                    case_id=case.id,
                    reason=LiveExclusionReason.FORCED_PLANNING_RECOVERY,
                )
        return None

    @staticmethod
    def build_report(
        *,
        run_id: str,
        started_at_utc: datetime,
        ended_at_utc: datetime,
        status: LiveRunStatus,
        corpus_schema_version: int,
        corpus_version: str,
        case_filter: str | None,
        model_id: str,
        prompts_used: list[PromptIdentity],
        exclusions: list[LiveCaseExclusion],
        case_results: list[RoutingCaseResult],
        incomplete_case_ids: list[str],
        unattempted_case_ids: list[str],
        operational_errors: list[OperationalErrorCategory],
    ) -> LiveEvalReport:
        stage_metrics = LiveRoutingEvaluationCore._stage_metrics(case_results)
        attempted = len(case_results)
        passed = sum(1 for result in case_results if result.passed)
        failed = attempted - passed
        distinct_prompts = LiveRoutingEvaluationCore._distinct_prompts(prompts_used)
        return LiveEvalReport(
            report_schema_version=1,
            run_id=run_id,
            started_at_utc=started_at_utc,
            ended_at_utc=ended_at_utc,
            status=status,
            corpus_schema_version=corpus_schema_version,
            corpus_version=corpus_version,
            case_filter=case_filter,
            model_id=model_id,
            prompts_used=distinct_prompts,
            exclusions=exclusions,
            case_results=case_results,
            incomplete_case_ids=list(incomplete_case_ids),
            unattempted_case_ids=list(unattempted_case_ids),
            stage_metrics=stage_metrics,
            attempted=attempted,
            passed=passed,
            failed=failed,
            excluded=len(exclusions),
            incomplete=len(incomplete_case_ids),
            operational_errors=list(operational_errors),
        )

    @staticmethod
    def format_console_summary(report: LiveEvalReport, artifact_path: Path) -> str:
        lines = [
            f"live_routing_eval status={report.status.value}",
            f"model_id={report.model_id} corpus={report.corpus_version}",
            (
                f"attempted={report.attempted} passed={report.passed} "
                f"failed={report.failed} excluded={report.excluded} "
                f"incomplete={report.incomplete}"
            ),
        ]
        for metrics in report.stage_metrics:
            lines.append(
                f"stage={metrics.stage.value} "
                f"pass_rate={metrics.pass_rate:.2f} "
                f"passed={metrics.passed}/{metrics.applicable} "
                f"failed={metrics.failed} blocked={metrics.blocked}",
            )
        lines.append(f"artifact={artifact_path}")
        return "\n".join(lines)

    @staticmethod
    def _stage_metrics(
        case_results: list[RoutingCaseResult],
    ) -> list[LiveStageMetrics]:
        metrics: list[LiveStageMetrics] = []
        for stage in STAGE_ORDER:
            passed = 0
            failed = 0
            applicable = 0
            blocked = 0
            for case_result in case_results:
                statuses = [
                    result.status
                    for result in case_result.stages
                    if result.stage is stage
                    and result.status is not StageStatus.NOT_APPLICABLE
                ]
                if not statuses:
                    continue
                applicable += 1
                if all(status is StageStatus.PASS for status in statuses):
                    passed += 1
                if any(status is StageStatus.FAIL for status in statuses):
                    failed += 1
                if any(status is StageStatus.BLOCKED for status in statuses):
                    blocked += 1
            pass_rate = (passed / applicable) if applicable else 0.0
            metrics.append(
                LiveStageMetrics(
                    stage=stage,
                    passed=passed,
                    failed=failed,
                    applicable=applicable,
                    blocked=blocked,
                    pass_rate=pass_rate,
                ),
            )
        return metrics

    @staticmethod
    def _distinct_prompts(
        prompts: list[PromptIdentity],
    ) -> list[PromptIdentity]:
        seen: set[tuple[str, str]] = set()
        ordered: list[PromptIdentity] = []
        for prompt in prompts:
            key = (prompt.prompt_id, prompt.prompt_hash)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(prompt)
        ordered.sort(key=lambda item: (item.prompt_id, item.prompt_hash))
        return ordered
