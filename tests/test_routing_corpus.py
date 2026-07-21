"""Corpus contract and coverage tests (TASK-020)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yoda.mind.agent.skills.catalog import SkillCatalog
from yoda.mind.evaluation.core import RoutingEvaluationCore
from yoda.mind.evaluation.corpus_provider import CorpusLoadError, RoutingCorpusProvider
from yoda.mind.evaluation.data import (
    ExpectedToolCall,
    IntentExpectation,
    NotApplicableExpectation,
    RoutingCorpus,
    RoutingMessage,
    RoutingTurn,
    StageExpectations,
    TurnInput,
    UserProfileFixture,
)

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "routing_evaluation" / "corpus-v1.json"
)
SKILLS_DIR = Path(__file__).resolve().parents[1] / "yoda" / "mind" / "agent" / "skills"


def _minimal_corpus_dict() -> dict:
    return {
        "schema_version": 1,
        "corpus_version": "0.0.1-test",
        "cases": [
            {
                "id": "minimal-chat",
                "language": "en",
                "purpose": "chat only",
                "turns": [
                    {
                        "id": "t1",
                        "event": "message",
                        "input": {"text": "Hi"},
                        "fixed_now_utc": "2026-07-20T12:00:00+00:00",
                        "profile": {},
                        "model_responses": [
                            {"stage": "intent", "raw": '{"intent": "chat"}'},
                        ],
                        "tool_results": [],
                        "expected": {
                            "intent": {"kind": "intent", "route": "chat"},
                            "selection": {
                                "kind": "not_applicable",
                                "reason": "chat_route",
                            },
                            "planning": {
                                "kind": "not_applicable",
                                "reason": "chat_route",
                            },
                            "execution": {
                                "kind": "not_applicable",
                                "reason": "chat_route",
                            },
                            "delivery": {
                                "kind": "not_applicable",
                                "reason": "chat_route",
                            },
                        },
                    },
                ],
            },
        ],
    }


def test_unknown_top_level_field_rejected() -> None:
    payload = _minimal_corpus_dict()
    payload["unexpected"] = True
    with pytest.raises(Exception):
        RoutingCorpus.model_validate(payload)


def test_minimal_valid_corpus_round_trips() -> None:
    corpus = RoutingCorpus.model_validate(_minimal_corpus_dict())
    assert corpus.schema_version == 1
    assert corpus.cases[0].id == "minimal-chat"


def test_tool_arguments_reject_non_json_values() -> None:
    with pytest.raises(Exception):
        ExpectedToolCall(
            tool_name="web_search",
            arguments={"invalid": object()},
        )


@pytest.mark.asyncio
async def test_load_invalid_json_identifies_case_and_field(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    provider = RoutingCorpusProvider()
    with pytest.raises(CorpusLoadError, match="invalid JSON"):
        await provider.load(bad)


@pytest.mark.asyncio
async def test_load_invalid_field_identifies_case_and_field(tmp_path: Path) -> None:
    payload = _minimal_corpus_dict()
    payload["cases"][0]["turns"][0]["expected"]["intent"]["route"] = "invalid"
    bad = tmp_path / "bad-field.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        CorpusLoadError,
        match=r"case=minimal-chat field=cases\.0\.turns\.0\.expected\.intent",
    ):
        await RoutingCorpusProvider().load(bad)


@pytest.mark.asyncio
async def test_load_valid_corpus(tmp_path: Path) -> None:
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(_minimal_corpus_dict()), encoding="utf-8")
    provider = RoutingCorpusProvider()
    corpus = await provider.load(path)
    assert corpus.corpus_version == "0.0.1-test"


def test_validate_corpus_reports_duplicate_case_id() -> None:
    payload = _minimal_corpus_dict()
    payload["cases"].append(payload["cases"][0])
    corpus = RoutingCorpus.model_validate(payload)
    issues = RoutingEvaluationCore.validate_corpus(
        corpus,
        frozenset(s.name for s in SkillCatalog.load_catalog(SKILLS_DIR)),
    )
    assert any("duplicate" in issue.message for issue in issues)


def test_validate_corpus_reports_orphan_tool_fixture() -> None:
    payload = _minimal_corpus_dict()
    payload["cases"][0]["turns"][0]["tool_results"] = [
        {"tool_name": "web_search", "output": "orphan", "success": True},
    ]
    corpus = RoutingCorpus.model_validate(payload)

    issues = RoutingEvaluationCore.validate_corpus(
        corpus,
        frozenset(s.name for s in SkillCatalog.load_catalog(SKILLS_DIR)),
    )

    assert any("tool fixture count" in issue.message for issue in issues)


@pytest.mark.asyncio
async def test_corpus_fixture_loads() -> None:
    provider = RoutingCorpusProvider()
    corpus = await provider.load(FIXTURE_PATH)
    assert corpus.schema_version == 1
    assert corpus.corpus_version == "1.1.1"


def test_corpus_has_en_and_ru_intent_families() -> None:
    corpus = RoutingCorpus.model_validate(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8")),
    )
    langs = {case.language.split("-")[0] for case in corpus.cases}
    assert "en" in langs
    assert "ru" in langs
    for lang in ("en", "ru"):
        intent_cases = [
            case
            for case in corpus.cases
            if case.language.startswith(lang)
            and any(
                isinstance(turn.expected.intent, IntentExpectation)
                for turn in case.turns
            )
        ]
        assert intent_cases, f"missing intent family for {lang}"


def test_corpus_covers_all_discovered_skills() -> None:
    corpus = RoutingCorpus.model_validate(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8")),
    )
    discovered = frozenset(s.name for s in SkillCatalog.load_catalog(SKILLS_DIR))
    referenced: set[str] = set()
    for case in corpus.cases:
        for turn in case.turns:
            selection = turn.expected.selection
            if hasattr(selection, "selected_skill") and selection.selected_skill:
                referenced.add(selection.selected_skill)
    assert discovered <= referenced


def test_corpus_contains_required_contrastive_families() -> None:
    corpus = RoutingCorpus.model_validate(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8")),
    )
    case_ids = {case.id for case in corpus.cases}

    assert {
        "en-selection-no-skill",
        "en-selection-protocol-corrected",
        "ru-selection-protocol-exhausted",
        "en-search-refinement",
        "ru-search-refinement",
        "en-strict-constraint-overrides-preference",
        "ru-execution-protocol-exhausted",
        "en-execution-unsupported",
        "en-delayed-dynamic-weather-check",
        "ru-relative-static-reminder",
        "july-20-recurring-spb-weather-accuweather",
    } <= case_ids


def test_corpus_covers_selection_successful_correction() -> None:
    corpus = RoutingCorpus.model_validate(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8")),
    )
    case = next(
        item
        for item in corpus.cases
        if item.id == "en-selection-protocol-corrected"
    )
    selection = case.turns[0].expected.selection
    assert selection.mode == "select_skill"
    assert selection.recovery == "corrected"
    assert [item.stage for item in case.turns[0].model_responses].count(
        "selection",
    ) >= 2


def test_july_20_covers_scheduled_constrained_execution() -> None:
    corpus = RoutingCorpus.model_validate(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8")),
    )
    case = next(
        item
        for item in corpus.cases
        if item.id == "july-20-recurring-spb-weather-accuweather"
    )

    assert len(case.turns) == 2
    scheduled = case.turns[1]
    assert scheduled.event == "scheduled_task"
    assert scheduled.input.request_constraints.strict_source_domains == [
        "accuweather.com",
    ]
    batches = scheduled.expected.planning.tool_batches
    assert len(batches) == 2
    assert all(
        call.arguments["include_domains"] == ["accuweather.com"]
        for batch in batches
        for call in batch.calls
    )


def test_relative_delay_case_omits_timezone_argument() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    case = next(
        item
        for item in payload["cases"]
        if item["id"] == "ru-relative-static-reminder"
    )
    planning_raw = next(
        item["raw"]
        for item in case["turns"][0]["model_responses"]
        if item["stage"] == "planning"
    )
    arguments = json.loads(planning_raw)["tool_calls"][0]["arguments"]

    assert arguments["delay_minutes"] == 15
    assert "timezone" not in arguments


def test_corpus_has_no_production_identifiers() -> None:
    text = FIXTURE_PATH.read_text(encoding="utf-8").lower()
    banned = ("telegram", "openrouter", "tavily", "redis", "chromadb")
    for token in banned:
        assert token not in text
