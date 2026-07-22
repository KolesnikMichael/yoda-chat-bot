"""Pure routing evaluation validation and scoring (TASK-020)."""

from __future__ import annotations

import ipaddress
import unicodedata
from urllib.parse import urlparse
from typing import Any

from yoda.mind.agent.data.agent_data import RequestConstraints
from yoda.mind.agent.data.outcome_data import (
    AllowedClaim,
    DeliveryPayload,
    OutcomeStatus,
    ProhibitedClaim,
)
from yoda.mind.evaluation.data import (
    STAGE_ORDER,
    CorpusIssue,
    DeliveryExpectation,
    ExecutionExpectation,
    ExecutionObservation,
    IntentExpectation,
    IntentObservation,
    NotApplicableExpectation,
    PlanningExpectation,
    PlanningObservation,
    RoutingCase,
    RoutingCaseResult,
    RoutingCorpus,
    RoutingEvaluationReport,
    RoutingObservation,
    RoutingTurn,
    SelectionExpectation,
    SelectionObservation,
    StageCounts,
    StageName,
    StageResult,
    StageStatus,
    StructuralDiff,
    TextExpectation,
    TurnObservation,
)


class RoutingEvaluationCore:
    @staticmethod
    def validate_corpus(
        corpus: RoutingCorpus,
        discovered_skills: frozenset[str],
    ) -> tuple[CorpusIssue, ...]:
        issues: list[CorpusIssue] = []
        seen_ids: set[str] = set()
        referenced_skills: set[str] = set()
        stage_families: dict[str, dict[StageName, set[str]]] = {
            "en": {stage: set() for stage in StageName},
            "ru": {stage: set() for stage in StageName},
        }

        for case in corpus.cases:
            if case.id in seen_ids:
                issues.append(
                    CorpusIssue(
                        case_id=case.id,
                        field_path="id",
                        message="duplicate case id",
                    ),
                )
            seen_ids.add(case.id)

            lang = case.language.lower().split("-")[0]
            if lang not in ("en", "ru"):
                issues.append(
                    CorpusIssue(
                        case_id=case.id,
                        field_path="language",
                        message=f"unsupported language tag: {case.language}",
                    ),
                )

            for turn in case.turns:
                for stage_name in StageName:
                    expectation = getattr(turn.expected, stage_name.value)
                    if isinstance(expectation, NotApplicableExpectation):
                        continue
                    if lang in stage_families:
                        stage_families[lang][stage_name].add(case.id)

                if isinstance(turn.expected.selection, SelectionExpectation):
                    skill = turn.expected.selection.selected_skill
                    if skill:
                        referenced_skills.add(skill)

                for response in turn.model_responses:
                    if not response.raw.strip():
                        issues.append(
                            CorpusIssue(
                                case_id=case.id,
                                field_path=f"turns[{turn.id}].model_responses",
                                message="empty model response raw payload",
                            ),
                        )
                issues.extend(
                    RoutingEvaluationCore._validate_turn_fixtures(case.id, turn),
                )

        for skill in discovered_skills:
            if skill not in referenced_skills:
                issues.append(
                    CorpusIssue(
                        case_id=None,
                        field_path="cases",
                        message=f"discovered skill never referenced: {skill}",
                    ),
                )

        for lang, families in stage_families.items():
            for stage_name, case_ids in families.items():
                if not case_ids:
                    issues.append(
                        CorpusIssue(
                            case_id=None,
                            field_path="cases",
                            message=(
                                f"no applicable {stage_name.value} cases for language {lang}"
                            ),
                        ),
                    )

        return tuple(issues)

    @staticmethod
    def _validate_turn_fixtures(
        case_id: str,
        turn: RoutingTurn,
    ) -> list[CorpusIssue]:
        issues: list[CorpusIssue] = []
        stages = [response.stage for response in turn.model_responses]
        stage_indexes = {"intent": 0, "selection": 1, "planning": 2}
        if any(
            stage_indexes[current] < stage_indexes[previous]
            for previous, current in zip(stages, stages[1:])
        ):
            issues.append(
                CorpusIssue(
                    case_id=case_id,
                    field_path=f"turns[{turn.id}].model_responses",
                    message="model response stages are out of order",
                ),
            )

        counts = {stage: stages.count(stage) for stage in stage_indexes}
        expected_intent = 1 if turn.event == "message" else 0
        if counts["intent"] != expected_intent:
            issues.append(
                CorpusIssue(
                    case_id=case_id,
                    field_path=f"turns[{turn.id}].model_responses",
                    message=(
                        f"intent fixture count {counts['intent']} "
                        f"does not match event {turn.event}"
                    ),
                ),
            )

        selection = turn.expected.selection
        expected_selection = 0
        if isinstance(selection, SelectionExpectation):
            expected_selection = 2 if selection.recovery != "none" else 1
        if counts["selection"] != expected_selection:
            issues.append(
                CorpusIssue(
                    case_id=case_id,
                    field_path=f"turns[{turn.id}].model_responses",
                    message=(
                        f"selection fixture count {counts['selection']} "
                        f"does not match expectation {expected_selection}"
                    ),
                ),
            )

        planning = turn.expected.planning
        minimum_planning = 0
        if isinstance(planning, PlanningExpectation):
            minimum_planning = 2 if planning.recovery != "none" else 1
        if (
            counts["planning"] < minimum_planning
            or (minimum_planning == 0 and counts["planning"] != 0)
        ):
            issues.append(
                CorpusIssue(
                    case_id=case_id,
                    field_path=f"turns[{turn.id}].model_responses",
                    message=(
                        f"planning fixture count {counts['planning']} "
                        f"does not satisfy minimum {minimum_planning}"
                    ),
                ),
            )

        expected_tool_names: list[str] = []
        if isinstance(planning, PlanningExpectation):
            expected_tool_names = [
                call.tool_name
                for batch in planning.tool_batches
                for call in batch.calls
            ]
        fixture_tool_names = [fixture.tool_name for fixture in turn.tool_results]
        if fixture_tool_names != expected_tool_names:
            issues.append(
                CorpusIssue(
                    case_id=case_id,
                    field_path=f"turns[{turn.id}].tool_results",
                    message=(
                        "tool fixture count/order does not match expected calls: "
                        f"expected={expected_tool_names} observed={fixture_tool_names}"
                    ),
                ),
            )
        return issues

    @staticmethod
    def score_case(
        case: RoutingCase,
        observation: RoutingObservation,
    ) -> RoutingCaseResult:
        stage_results: list[StageResult] = []
        first_divergence: StageName | None = None

        for turn in case.turns:
            turn_obs = observation.turn(turn.id)
            turn_divergence: StageName | None = None

            for stage_name in STAGE_ORDER:
                expectation = getattr(turn.expected, stage_name.value)
                if isinstance(expectation, NotApplicableExpectation):
                    stage_results.append(
                        StageResult(
                            stage=stage_name,
                            turn_id=turn.id,
                            status=StageStatus.NOT_APPLICABLE,
                            blocked_by=None,
                            diffs=(),
                        ),
                    )
                    continue

                stage_observation = (
                    None
                    if turn_obs is None
                    else getattr(turn_obs, stage_name.value)
                )
                if turn_divergence is not None and stage_observation is None:
                    stage_results.append(
                        StageResult(
                            stage=stage_name,
                            turn_id=turn.id,
                            status=StageStatus.BLOCKED,
                            blocked_by=turn_divergence,
                            diffs=(),
                        ),
                    )
                    continue

                diffs = RoutingEvaluationCore._score_stage(
                    stage_name,
                    expectation,
                    turn_obs,
                )
                if diffs:
                    stage_results.append(
                        StageResult(
                            stage=stage_name,
                            turn_id=turn.id,
                            status=StageStatus.FAIL,
                            blocked_by=None,
                            diffs=tuple(diffs),
                        ),
                    )
                    if first_divergence is None:
                        first_divergence = stage_name
                    turn_divergence = stage_name
                else:
                    stage_results.append(
                        StageResult(
                            stage=stage_name,
                            turn_id=turn.id,
                            status=StageStatus.PASS,
                            blocked_by=None,
                            diffs=(),
                        ),
                    )

        passed = all(
            result.status in (StageStatus.PASS, StageStatus.NOT_APPLICABLE)
            for result in stage_results
        )
        return RoutingCaseResult(
            case_id=case.id,
            stages=tuple(stage_results),
            first_divergence=first_divergence,
            passed=passed,
        )

    @staticmethod
    def aggregate(
        corpus_version: str,
        case_results: list[RoutingCaseResult],
    ) -> RoutingEvaluationReport:
        counts = {
            stage: StageCounts(passed=0, failed=0, applicable=0, blocked=0)
            for stage in StageName
        }
        for case_result in case_results:
            for stage in StageName:
                statuses = [
                    result.status
                    for result in case_result.stages
                    if result.stage is stage
                    and result.status is not StageStatus.NOT_APPLICABLE
                ]
                if not statuses:
                    continue
                bucket = counts[stage]
                counts[stage] = StageCounts(
                    passed=bucket.passed
                    + int(all(status is StageStatus.PASS for status in statuses)),
                    failed=bucket.failed
                    + int(any(status is StageStatus.FAIL for status in statuses)),
                    applicable=bucket.applicable + 1,
                    blocked=bucket.blocked
                    + int(any(status is StageStatus.BLOCKED for status in statuses)),
                )
        return RoutingEvaluationReport(
            corpus_version=corpus_version,
            case_results=tuple(case_results),
            stage_counts=counts,
        )

    @staticmethod
    def format_summary(
        report: RoutingEvaluationReport,
        *,
        include_values: bool = False,
    ) -> str:
        lines = [f"corpus_version={report.corpus_version}"]
        passed_cases = sum(result.passed for result in report.case_results)
        total_cases = len(report.case_results)
        lines.append(
            f"cases: passed={passed_cases} "
            f"failed={total_cases - passed_cases} total={total_cases}",
        )
        for case_result in report.case_results:
            if case_result.passed:
                continue
            lines.append(f"case_id={case_result.case_id}")
            if case_result.first_divergence is not None:
                lines.append(
                    f"first_divergence={case_result.first_divergence.value}",
                )
            for stage_result in case_result.stages:
                if stage_result.status not in (
                    StageStatus.FAIL,
                    StageStatus.BLOCKED,
                ):
                    continue
                lines.append(
                    f"  turn={stage_result.turn_id} "
                    f"stage={stage_result.stage.value} "
                    f"status={stage_result.status.value}",
                )
                if stage_result.blocked_by is not None:
                    lines.append(
                        f"    blocked_by={stage_result.blocked_by.value}",
                    )
                for diff in stage_result.diffs:
                    if include_values:
                        lines.append(
                            f"    diff path={diff.path} "
                            f"expected={diff.expected!r} observed={diff.observed!r}",
                        )
                    else:
                        lines.append(f"    diff path={diff.path}")
        lines.append("stage_counts:")
        for stage_name in STAGE_ORDER:
            bucket = report.stage_counts[stage_name]
            lines.append(
                f"  {stage_name.value}: passed={bucket.passed} "
                f"failed={bucket.failed} applicable={bucket.applicable} "
                f"blocked={bucket.blocked}",
            )
        return "\n".join(lines)

    @staticmethod
    def _score_stage(
        stage_name: StageName,
        expectation: object,
        turn_obs: TurnObservation | None,
    ) -> list[StructuralDiff]:
        if turn_obs is None:
            return [
                StructuralDiff(
                    path=f"{stage_name.value}",
                    expected="observation present",
                    observed=None,
                ),
            ]
        if stage_name is StageName.INTENT:
            assert isinstance(expectation, IntentExpectation)
            return RoutingEvaluationCore._score_intent(
                expectation,
                turn_obs.intent,
            )
        if stage_name is StageName.SELECTION:
            assert isinstance(expectation, SelectionExpectation)
            return RoutingEvaluationCore._score_selection(
                expectation,
                turn_obs.selection,
            )
        if stage_name is StageName.PLANNING:
            assert isinstance(expectation, PlanningExpectation)
            return RoutingEvaluationCore._score_planning(
                expectation,
                turn_obs.planning,
            )
        if stage_name is StageName.EXECUTION:
            assert isinstance(expectation, ExecutionExpectation)
            return RoutingEvaluationCore._score_execution(
                expectation,
                turn_obs.execution,
            )
        assert isinstance(expectation, DeliveryExpectation)
        return RoutingEvaluationCore._score_delivery(
            expectation,
            turn_obs.delivery,
        )

    @staticmethod
    def _score_intent(
        expected: IntentExpectation,
        observed: IntentObservation | None,
    ) -> list[StructuralDiff]:
        if observed is None:
            return [
                StructuralDiff("intent.route", expected.route, None),
            ]
        if observed.route != expected.route:
            return [
                StructuralDiff("intent.route", expected.route, observed.route),
            ]
        return []

    @staticmethod
    def _score_selection(
        expected: SelectionExpectation,
        observed: SelectionObservation | None,
    ) -> list[StructuralDiff]:
        if observed is None:
            return [StructuralDiff("selection.mode", expected.mode, None)]
        diffs: list[StructuralDiff] = []
        if observed.mode != expected.mode:
            diffs.append(
                StructuralDiff("selection.mode", expected.mode, observed.mode),
            )
        if expected.mode == "select_skill":
            decision = observed.decision
            if decision is None:
                diffs.append(
                    StructuralDiff("selection.decision", "present", None),
                )
            else:
                if decision.selected_skill != expected.selected_skill:
                    diffs.append(
                        StructuralDiff(
                            "selection.selected_skill",
                            expected.selected_skill,
                            decision.selected_skill,
                        ),
                    )
                if expected.distilled_task is not None:
                    diffs.extend(
                        RoutingEvaluationCore._text_diffs(
                            "selection.distilled_task",
                            expected.distilled_task,
                            decision.distilled_task or "",
                        ),
                    )
                diffs.extend(
                    RoutingEvaluationCore._constraint_diffs(
                        expected.request_constraints,
                        decision.request_constraints,
                    ),
                )
        if observed.recovery != expected.recovery:
            diffs.append(
                StructuralDiff(
                    "selection.recovery",
                    expected.recovery,
                    observed.recovery,
                ),
            )
        return diffs

    @staticmethod
    def _score_planning(
        expected: PlanningExpectation,
        observed: PlanningObservation | None,
    ) -> list[StructuralDiff]:
        if (
            observed is not None
            and expected.recovery == "exhausted"
            and observed.recovery == "exhausted"
            and not observed.decisions
            and not observed.tool_calls
        ):
            return []
        if observed is None or not observed.decisions:
            return [
                StructuralDiff(
                    "planning.decisions",
                    "non-empty",
                    None if observed is None else len(observed.decisions),
                ),
            ]
        decision = observed.decisions[-1]
        if decision.mode not in expected.accepted_modes:
            return [
                StructuralDiff(
                    "planning.mode",
                    expected.accepted_modes,
                    decision.mode,
                ),
            ]
        if expected.tool_batches:
            diffs = RoutingEvaluationCore._tool_batch_diffs(
                expected.tool_batches,
                observed.tool_calls,
            )
            if diffs:
                return diffs
        if observed.recovery != expected.recovery:
            return [
                StructuralDiff(
                    "planning.recovery",
                    expected.recovery,
                    observed.recovery,
                ),
            ]
        return []

    @staticmethod
    def _score_execution(
        expected: ExecutionExpectation,
        observed: ExecutionObservation | None,
    ) -> list[StructuralDiff]:
        if observed is None or observed.agent_result is None:
            return [
                StructuralDiff("execution.agent_result", "present", None),
            ]
        result = observed.agent_result
        if expected.result == "clarification":
            if result.clarification is None:
                return [
                    StructuralDiff(
                        "execution.result",
                        "clarification",
                        "outcome" if result.outcome else None,
                    ),
                ]
            return []
        if result.clarification is not None:
            return [
                StructuralDiff(
                    "execution.result",
                    expected.result,
                    "clarification",
                ),
            ]
        if result.outcome is None:
            return [StructuralDiff("execution.outcome", "present", None)]
        outcome = result.outcome
        if expected.result == "success":
            if outcome.status is not OutcomeStatus.SUCCESS:
                return [
                    StructuralDiff(
                        "execution.status",
                        OutcomeStatus.SUCCESS,
                        outcome.status,
                    ),
                ]
        elif expected.result == "failure":
            if outcome.status is not OutcomeStatus.FAILURE:
                return [
                    StructuralDiff(
                        "execution.status",
                        OutcomeStatus.FAILURE,
                        outcome.status,
                    ),
                ]
        diffs: list[StructuralDiff] = []
        if expected.operation is not None and outcome.operation != expected.operation:
            diffs.append(
                StructuralDiff(
                    "execution.operation",
                    expected.operation,
                    outcome.operation,
                ),
            )
        if expected.result_kind is not None and outcome.result_kind != expected.result_kind:
            diffs.append(
                StructuralDiff(
                    "execution.result_kind",
                    expected.result_kind,
                    outcome.result_kind,
                ),
            )
        if expected.job_kind is not None and outcome.job_kind != expected.job_kind:
            diffs.append(
                StructuralDiff(
                    "execution.job_kind",
                    expected.job_kind,
                    outcome.job_kind,
                ),
            )
        if (
            expected.scheduled_operation is not None
            and outcome.scheduled_operation != expected.scheduled_operation
        ):
            diffs.append(
                StructuralDiff(
                    "execution.scheduled_operation",
                    expected.scheduled_operation,
                    outcome.scheduled_operation,
                ),
            )
        if expected.schedule is not None:
            diffs.extend(
                RoutingEvaluationCore._text_diffs(
                    "execution.schedule",
                    expected.schedule,
                    outcome.schedule or "",
                ),
            )
        if (
            expected.failure_category is not None
            and outcome.failure_category != expected.failure_category
        ):
            diffs.append(
                StructuralDiff(
                    "execution.failure_category",
                    expected.failure_category,
                    outcome.failure_category,
                ),
            )
        if expected.next_step is not None and outcome.next_step != expected.next_step:
            diffs.append(
                StructuralDiff(
                    "execution.next_step",
                    expected.next_step,
                    outcome.next_step,
                ),
            )
        return diffs

    @staticmethod
    def _score_delivery(
        expected: DeliveryExpectation,
        observed: DeliveryObservation | None,
    ) -> list[StructuralDiff]:
        if observed is None or observed.payload is None:
            return [StructuralDiff("delivery.payload", "present", None)]
        payload = observed.payload
        diffs: list[StructuralDiff] = []
        if payload.status != expected.status:
            diffs.append(
                StructuralDiff("delivery.status", expected.status, payload.status),
            )
        for fact in expected.facts:
            if fact not in payload.facts:
                diffs.append(
                    StructuralDiff("delivery.facts", fact, tuple(payload.facts)),
                )
        if set(expected.allowed_claims) != set(payload.allowed_claims):
            diffs.append(
                StructuralDiff(
                    "delivery.allowed_claims",
                    tuple(expected.allowed_claims),
                    tuple(payload.allowed_claims),
                ),
            )
        if set(expected.prohibited_claims) != set(payload.prohibited_claims):
            diffs.append(
                StructuralDiff(
                    "delivery.prohibited_claims",
                    tuple(expected.prohibited_claims),
                    tuple(payload.prohibited_claims),
                ),
            )
        diffs.extend(
            RoutingEvaluationCore._text_diffs(
                "delivery.source_text",
                expected.source_text,
                payload.source_text,
            ),
        )
        return diffs

    @staticmethod
    def fragments_match(text: str, expectation: TextExpectation) -> list[str]:
        folded = RoutingEvaluationCore._casefold(text)
        failures: list[str] = []
        for fragment in expectation.required_fragments:
            if RoutingEvaluationCore._casefold(fragment) not in folded:
                failures.append(f"missing required fragment: {fragment!r}")
        for fragment in expectation.prohibited_fragments:
            if RoutingEvaluationCore._casefold(fragment) in folded:
                failures.append(f"found prohibited fragment: {fragment!r}")
        return failures

    @staticmethod
    def argument_is_subset(expected: dict[str, Any], observed: dict[str, Any]) -> bool:
        for key, expected_value in expected.items():
            if key not in observed:
                return False
            if not RoutingEvaluationCore._value_subset(expected_value, observed[key]):
                return False
        return True

    @staticmethod
    def tool_batches_match(
        batches: list,
        observed_calls: list,
    ) -> list[StructuralDiff]:
        return RoutingEvaluationCore._tool_batch_diffs(batches, observed_calls)

    @staticmethod
    def delivery_claims_violated(
        payload: DeliveryPayload,
        prohibited: list[ProhibitedClaim],
    ) -> list[ProhibitedClaim]:
        missing = [claim for claim in prohibited if claim not in payload.prohibited_claims]
        return missing

    @staticmethod
    def normalize_domains(constraints: RequestConstraints) -> RequestConstraints:
        strict: list[str] = []
        seen_strict: set[str] = set()
        for item in constraints.strict_source_domains:
            host = RoutingEvaluationCore._normalize_host(item)
            key = host.casefold()
            if key in seen_strict:
                continue
            seen_strict.add(key)
            strict.append(host)

        soft: list[str] = []
        seen_soft: set[str] = set()
        for item in constraints.soft_source_domains:
            host = RoutingEvaluationCore._normalize_host(item)
            key = host.casefold()
            if key in seen_strict or key in seen_soft:
                continue
            seen_soft.add(key)
            soft.append(host)

        return RequestConstraints(
            strict_source_domains=strict,
            soft_source_domains=soft,
        )

    @staticmethod
    def _text_diffs(
        prefix: str,
        expectation: TextExpectation,
        text: str,
    ) -> list[StructuralDiff]:
        failures = RoutingEvaluationCore.fragments_match(text, expectation)
        return [
            StructuralDiff(prefix, message, text)
            for message in failures
        ]

    @staticmethod
    def _constraint_diffs(
        expected: RequestConstraints,
        observed: RequestConstraints,
    ) -> list[StructuralDiff]:
        try:
            exp_norm = RoutingEvaluationCore.normalize_domains(expected)
            obs_norm = RoutingEvaluationCore.normalize_domains(observed)
        except ValueError as exc:
            return [
                StructuralDiff(
                    "selection.request_constraints",
                    "valid constraints",
                    str(exc),
                ),
            ]
        diffs: list[StructuralDiff] = []
        if exp_norm.strict_source_domains != obs_norm.strict_source_domains:
            diffs.append(
                StructuralDiff(
                    "selection.request_constraints.strict_source_domains",
                    exp_norm.strict_source_domains,
                    obs_norm.strict_source_domains,
                ),
            )
        if exp_norm.soft_source_domains != obs_norm.soft_source_domains:
            diffs.append(
                StructuralDiff(
                    "selection.request_constraints.soft_source_domains",
                    exp_norm.soft_source_domains,
                    obs_norm.soft_source_domains,
                ),
            )
        return diffs

    @staticmethod
    def _tool_batch_diffs(batches: list, observed_calls: list) -> list[StructuralDiff]:
        diffs: list[StructuralDiff] = []
        observed_index = 0
        for index, batch in enumerate(batches):
            expected_calls = [
                (call.tool_name, call.arguments) for call in batch.calls
            ]
            observed_slice = [
                (call.tool_name, call.arguments) for call in observed_calls
            ][observed_index : observed_index + len(expected_calls)]
            observed_index += len(expected_calls)
            if batch.matching == "ordered":
                if len(expected_calls) != len(observed_slice):
                    diffs.append(
                        StructuralDiff(
                            f"planning.tool_batches[{index}]",
                            len(expected_calls),
                            len(observed_slice),
                        ),
                    )
                    continue
                window = observed_slice[: len(expected_calls)]
                for call_index, (exp_name, exp_args) in enumerate(expected_calls):
                    obs_name, obs_args = window[call_index]
                    if exp_name != obs_name:
                        diffs.append(
                            StructuralDiff(
                                f"planning.tool_batches[{index}].calls[{call_index}].tool_name",
                                exp_name,
                                obs_name,
                            ),
                        )
                    elif not RoutingEvaluationCore.argument_is_subset(
                        exp_args,
                        obs_args,
                    ):
                        diffs.append(
                            StructuralDiff(
                                f"planning.tool_batches[{index}].calls[{call_index}].arguments",
                                exp_args,
                                obs_args,
                            ),
                        )
            else:
                unmatched = list(observed_slice)
                for exp_name, exp_args in expected_calls:
                    match_index = None
                    for obs_index, (obs_name, obs_args) in enumerate(unmatched):
                        if exp_name == obs_name and RoutingEvaluationCore.argument_is_subset(
                            exp_args,
                            obs_args,
                        ):
                            match_index = obs_index
                            break
                    if match_index is None:
                        diffs.append(
                            StructuralDiff(
                                f"planning.tool_batches[{index}]",
                                f"{exp_name} with subset args",
                                unmatched,
                            ),
                        )
                    else:
                        unmatched.pop(match_index)
        if observed_index < len(observed_calls):
            diffs.append(
                StructuralDiff(
                    "planning.tool_batches.extra_calls",
                    0,
                    len(observed_calls) - observed_index,
                ),
            )
        return diffs

    @staticmethod
    def _value_subset(expected: Any, observed: Any) -> bool:
        if isinstance(expected, dict):
            if not isinstance(observed, dict):
                return False
            return RoutingEvaluationCore.argument_is_subset(expected, observed)
        if isinstance(expected, list):
            if not isinstance(observed, list):
                return False
            if len(expected) > len(observed):
                return False
            return all(
                RoutingEvaluationCore._value_subset(exp_item, obs_item)
                for exp_item, obs_item in zip(expected, observed)
            )
        if isinstance(expected, str) and isinstance(observed, str):
            if expected == observed:
                return True
            if expected.startswith("domain:"):
                return RoutingEvaluationCore._domains_equal(expected, observed)
            return RoutingEvaluationCore._casefold(expected) in RoutingEvaluationCore._casefold(
                observed,
            )
        return expected == observed

    @staticmethod
    def _domains_equal(expected_marker: str, observed_value: str) -> bool:
        expected_domains = expected_marker.removeprefix("domain:").split(",")
        if isinstance(observed_value, list):
            observed_domains = observed_value
        else:
            observed_domains = [observed_value]
        try:
            exp_norm = RoutingEvaluationCore.normalize_domains(
                RequestConstraints(strict_source_domains=list(expected_domains)),
            ).strict_source_domains
            obs_norm = RoutingEvaluationCore.normalize_domains(
                RequestConstraints(strict_source_domains=list(observed_domains)),
            ).strict_source_domains
        except ValueError:
            return False
        return set(exp_norm) == set(obs_norm)

    @staticmethod
    def _normalize_host(value: str) -> str:
        raw = value.strip()
        if not raw:
            raise ValueError("empty host")
        if "*" in raw or raw.startswith("."):
            raise ValueError(f"invalid host form: {value!r}")

        candidate = raw
        if "://" not in candidate and "/" not in candidate and "@" not in candidate:
            host = candidate
        else:
            parsed = urlparse(
                candidate if "://" in candidate else f"https://{candidate}",
            )
            if parsed.scheme not in ("http", "https"):
                raise ValueError(f"unsupported scheme: {value!r}")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError(f"credentials not allowed: {value!r}")
            if not parsed.hostname:
                raise ValueError(f"missing hostname: {value!r}")
            host = parsed.hostname

        if host.endswith("."):
            host = host[:-1]
        if not host:
            raise ValueError(f"empty host after normalize: {value!r}")

        try:
            ipaddress.ip_address(host)
            raise ValueError(f"IP literals not allowed: {value!r}")
        except ValueError as exc:
            if "IP literals" in str(exc):
                raise

        labels = host.split(".")
        if any(
            not label or not RoutingEvaluationCore._is_dns_label(label)
            for label in labels
        ):
            raise ValueError(f"invalid DNS labels: {value!r}")

        try:
            return host.lower().encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(f"invalid IDNA host: {value!r}") from exc

    @staticmethod
    def _is_dns_label(label: str) -> bool:
        if len(label) > 63 or label.startswith("-") or label.endswith("-"):
            return False
        return all(character.isalnum() or character == "-" for character in label)

    @staticmethod
    def _casefold(text: str) -> str:
        return unicodedata.normalize("NFKC", text).casefold()
