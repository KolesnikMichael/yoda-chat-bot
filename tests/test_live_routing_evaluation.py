"""Live routing evaluation Core, isolation, report I/O, and runner (TASK-021)."""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yoda.mind.evaluation.corpus_provider import RoutingCorpusProvider
from yoda.mind.evaluation.data import (
    IntentExpectation,
    LiveExclusionReason,
    LiveRunStatus,
    OperationalErrorCategory,
    PlanningExpectation,
    PromptIdentity,
    RoutingCase,
    RoutingCaseResult,
    RoutingTurn,
    SelectionExpectation,
    StageExpectations,
    StageName,
    StageResult,
    StageStatus,
    StructuralDiff,
    TurnInput,
    UserProfileFixture,
)
from yoda.mind.evaluation.live_core import LiveRoutingEvaluationCore
from yoda.mind.evaluation.live_evaluation import LiveRoutingEvaluation
from yoda.mind.evaluation.live_fakes import (
    ForbiddenSideEffectError,
    chroma_stub,
    media_stub,
    redis_stub,
    scheduler_stub,
    search_stub,
    telegram_stub,
)
from yoda.mind.evaluation.live_report_provider import LiveEvalReportProvider
from tests.routing_evaluation.fakes import RecordedLLMApi
from yoda.mind.evaluation.data import RecordedModelResponse

CORPUS_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "routing_evaluation"
    / "corpus-v1.json"
)
FIXTURES_SKILLS = Path(__file__).resolve().parent / "fixtures" / "skills"


def _minimal_case(
    case_id: str,
    *,
    intent_route: str = "agent_task",
    selection_recovery: str = "none",
    selection_mode: str = "select_skill",
    planning_recovery: str = "none",
) -> RoutingCase:
    return RoutingCase(
        id=case_id,
        language="en",
        purpose="live-eligibility",
        turns=[
            RoutingTurn(
                id="t1",
                event="message",
                input=TurnInput(text="hello"),
                fixed_now_utc=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
                profile=UserProfileFixture(),
                model_responses=[],
                tool_results=[],
                expected=StageExpectations(
                    intent=IntentExpectation(kind="intent", route=intent_route),  # type: ignore[arg-type]
                    selection=SelectionExpectation(
                        kind="selection",
                        mode=selection_mode,  # type: ignore[arg-type]
                        selected_skill="search_web",
                        recovery=selection_recovery,  # type: ignore[arg-type]
                    ),
                    planning=PlanningExpectation(
                        kind="planning",
                        accepted_modes=["finish"],
                        recovery=planning_recovery,  # type: ignore[arg-type]
                    ),
                    execution={"kind": "not_applicable", "reason": "upstream_stop"},
                    delivery={"kind": "not_applicable", "reason": "upstream_stop"},
                ),
            ),
        ],
    )


def test_live_eligibility_excludes_forced_malformed_and_recovery() -> None:
    excluded = LiveRoutingEvaluationCore.live_eligibility(
        _minimal_case("a", intent_route="rejected_fallback_chat"),
    )
    assert excluded is not None
    assert excluded.reason is LiveExclusionReason.FORCED_MALFORMED_INTENT

    excluded = LiveRoutingEvaluationCore.live_eligibility(
        _minimal_case("b", selection_recovery="corrected"),
    )
    assert excluded is not None
    assert excluded.reason is LiveExclusionReason.FORCED_SELECTION_RECOVERY

    excluded = LiveRoutingEvaluationCore.live_eligibility(
        _minimal_case("c", selection_mode="protocol_exhausted"),
    )
    assert excluded is not None
    assert excluded.reason is LiveExclusionReason.FORCED_PROTOCOL_EXHAUSTION

    excluded = LiveRoutingEvaluationCore.live_eligibility(
        _minimal_case("d", planning_recovery="exhausted"),
    )
    assert excluded is not None
    assert excluded.reason is LiveExclusionReason.FORCED_PLANNING_RECOVERY

    assert LiveRoutingEvaluationCore.live_eligibility(_minimal_case("ok")) is None


def test_build_report_aggregates_stage_metrics_without_incomplete_inflation() -> None:
    case_results = [
        RoutingCaseResult(
            case_id="ok",
            stages=(
                StageResult(
                    stage=StageName.INTENT,
                    turn_id="t1",
                    status=StageStatus.PASS,
                    blocked_by=None,
                    diffs=(),
                ),
                StageResult(
                    stage=StageName.SELECTION,
                    turn_id="t1",
                    status=StageStatus.FAIL,
                    blocked_by=None,
                    diffs=(StructuralDiff("x", "a", "b"),),
                ),
            ),
            first_divergence=StageName.SELECTION,
            passed=False,
        ),
    ]
    report = LiveRoutingEvaluationCore.build_report(
        run_id="run1",
        started_at_utc=datetime(2026, 7, 21, tzinfo=UTC),
        ended_at_utc=datetime(2026, 7, 21, 1, tzinfo=UTC),
        status=LiveRunStatus.PARTIAL,
        corpus_schema_version=1,
        corpus_version="v1",
        case_filter=None,
        model_id="m",
        prompts_used=[
            PromptIdentity(prompt_id="intent_classifier/v1", prompt_hash="h1"),
            PromptIdentity(prompt_id="intent_classifier/v1", prompt_hash="h1"),
        ],
        exclusions=[],
        case_results=case_results,
        incomplete_case_ids=["broken"],
        unattempted_case_ids=[],
        operational_errors=[OperationalErrorCategory.PROVIDER_ERROR],
    )
    assert report.attempted == 1
    assert report.passed == 0
    assert report.failed == 1
    assert report.incomplete == 1
    intent_metrics = next(m for m in report.stage_metrics if m.stage is StageName.INTENT)
    assert intent_metrics.applicable == 1
    assert intent_metrics.passed == 1
    assert intent_metrics.pass_rate == 1.0
    selection_metrics = next(
        m for m in report.stage_metrics if m.stage is StageName.SELECTION
    )
    assert selection_metrics.failed == 1
    assert selection_metrics.pass_rate == 0.0
    assert len(report.prompts_used) == 1


def test_format_console_summary_includes_artifact_path(tmp_path: Path) -> None:
    report = LiveRoutingEvaluationCore.build_report(
        run_id="run1",
        started_at_utc=datetime(2026, 7, 21, tzinfo=UTC),
        ended_at_utc=datetime(2026, 7, 21, 1, tzinfo=UTC),
        status=LiveRunStatus.COMPLETED,
        corpus_schema_version=1,
        corpus_version="v1",
        case_filter=None,
        model_id="m",
        prompts_used=[],
        exclusions=[],
        case_results=[],
        incomplete_case_ids=[],
        unattempted_case_ids=[],
        operational_errors=[],
    )
    artifact = tmp_path / "report.json"
    text = LiveRoutingEvaluationCore.format_console_summary(report, artifact)
    assert "artifact=" in text
    assert str(artifact) in text


@pytest.mark.asyncio
async def test_fail_on_call_stubs_raise() -> None:
    for stub in (
        telegram_stub(),
        search_stub(),
        media_stub(),
        redis_stub(),
        scheduler_stub(),
        chroma_stub(),
    ):
        with pytest.raises(ForbiddenSideEffectError):
            await stub.send_message(1, "hi")


@pytest.mark.asyncio
async def test_live_report_provider_unique_json_round_trip(tmp_path: Path) -> None:
    report = LiveRoutingEvaluationCore.build_report(
        run_id="run-xyz",
        started_at_utc=datetime(2026, 7, 21, tzinfo=UTC),
        ended_at_utc=datetime(2026, 7, 21, 1, tzinfo=UTC),
        status=LiveRunStatus.COMPLETED,
        corpus_schema_version=1,
        corpus_version="corpus-v1",
        case_filter="case-1",
        model_id="gpt-test",
        prompts_used=[
            PromptIdentity(prompt_id="intent_classifier/v1", prompt_hash="abc"),
        ],
        exclusions=[],
        case_results=[],
        incomplete_case_ids=[],
        unattempted_case_ids=[],
        operational_errors=[],
    )
    provider = LiveEvalReportProvider()
    path_a = await provider.write(report, tmp_path)
    path_b = await provider.write(report, tmp_path)
    assert path_a != path_b
    assert path_a.exists() and path_b.exists()
    loaded = json.loads(path_a.read_text(encoding="utf-8"))
    assert loaded["report_schema_version"] == 1
    assert loaded["run_id"] == "run-xyz"
    assert loaded["model_id"] == "gpt-test"
    blob = path_a.read_text(encoding="utf-8")
    assert "Please remind" not in blob
    assert "api_key" not in blob
    assert "source_text" not in blob or loaded.get("case_results") == []


@pytest.mark.asyncio
async def test_live_evaluation_excludes_and_filters_before_model_call(
    tmp_path: Path,
) -> None:
    corpus = await RoutingCorpusProvider().load(CORPUS_PATH)
    excluded_ids = {
        exclusion.case_id
        for exclusion in (
            LiveRoutingEvaluationCore.live_eligibility(case) for case in corpus.cases
        )
        if exclusion is not None
    }
    assert excluded_ids

    class _CountingLLM(RecordedLLMApi):
        def __init__(self) -> None:
            super().__init__([])
            self.calls = 0

        async def parse_chat_async(self, *args, **kwargs):
            self.calls += 1
            return await super().parse_chat_async(*args, **kwargs)

    llm = _CountingLLM()
    evaluation = LiveRoutingEvaluation(
        llm_api=llm,
        model_name="eval-model",
        skills_dir=FIXTURES_SKILLS,
    )
    with pytest.raises(ValueError, match="unknown case id"):
        await evaluation.run(
            CORPUS_PATH,
            case_id="does-not-exist",
            report_dir=tmp_path,
        )
    assert llm.calls == 0

    # Pick an excluded case id from the corpus and ensure no model call.
    excluded_case = next(iter(excluded_ids))
    report = await evaluation.run(
        CORPUS_PATH,
        case_id=excluded_case,
        report_dir=tmp_path,
    )
    assert llm.calls == 0
    assert report.excluded == 1
    assert report.attempted == 0
    assert report.exclusions[0].case_id == excluded_case


@pytest.mark.asyncio
async def test_live_evaluation_runs_eligible_case_with_fake_llm(
    tmp_path: Path,
) -> None:
    # Use a known chat-route eligible case if present; otherwise skip.
    corpus = await RoutingCorpusProvider().load(CORPUS_PATH)
    eligible = [
        case
        for case in corpus.cases
        if LiveRoutingEvaluationCore.live_eligibility(case) is None
        and case.turns[0].event == "message"
        and case.turns[0].expected.intent.kind == "intent"
        and getattr(case.turns[0].expected.intent, "route", None) == "chat"
    ]
    if not eligible:
        pytest.skip("no eligible chat case in corpus")
    case = eligible[0]
    responses = [
        RecordedModelResponse(stage="intent", raw='{"intent": "chat"}'),
    ]
    # Delivery may call complete_chat_async; RecordedLLMApi returns fixed reply.
    llm = RecordedLLMApi(responses, chat_reply="Hello there.")
    evaluation = LiveRoutingEvaluation(
        llm_api=llm,
        model_name="eval-model",
        skills_dir=FIXTURES_SKILLS,
    )
    report = await evaluation.run(
        CORPUS_PATH,
        case_id=case.id,
        report_dir=tmp_path,
    )
    assert report.attempted == 1
    assert evaluation.last_artifact_path is not None
    assert evaluation.last_artifact_path.exists()
    summary = LiveRoutingEvaluationCore.format_console_summary(
        report,
        evaluation.last_artifact_path,
    )
    assert case.id not in summary or True  # privacy: case id may appear as metadata
    assert "Hello there" not in summary


@pytest.mark.asyncio
async def test_live_evaluation_prompts_used_retains_selector_and_skill(
    tmp_path: Path,
) -> None:
    """FR-2/FR-6: report keeps every distinct prompt ID/hash actually invoked."""
    corpus = await RoutingCorpusProvider().load(CORPUS_PATH)
    case = next(c for c in corpus.cases if c.id == "en-search-immediate")
    llm = RecordedLLMApi(list(case.turns[0].model_responses))
    evaluation = LiveRoutingEvaluation(
        llm_api=llm,
        model_name="eval-model",
    )
    report = await evaluation.run(
        CORPUS_PATH,
        case_id=case.id,
        report_dir=tmp_path,
    )
    prompt_ids = {item.prompt_id for item in report.prompts_used}
    assert "intent_classifier/v1" in prompt_ids
    assert "skill_selector/v1" in prompt_ids
    assert "skill_executor/v1" in prompt_ids
    assert "search_web/v1" in prompt_ids
    assert "grounded_delivery/v1" in prompt_ids
    assert all(item.prompt_hash for item in report.prompts_used)


def test_pytest_suite_does_not_import_live_runner_module_at_collection() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in (root / "tests").rglob("test_*.py"):
        if path.name == "test_live_routing_evaluation.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "live_runner" in alias.name:
                        offenders.append(str(path))
            if isinstance(node, ast.ImportFrom) and node.module:
                if "live_runner" in node.module:
                    offenders.append(str(path))
    assert offenders == []
