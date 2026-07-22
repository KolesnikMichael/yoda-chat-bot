"""Tests for ExecutionContextCore preference/constraint policy."""

from __future__ import annotations

import pytest

from yoda.mind.agent.core.execution_context import ExecutionContextCore
from yoda.mind.agent.data.agent_data import (
    AgentPhase,
    ProtocolIssueCategory,
    RequestConstraints,
    ToolCallRequest,
)
from yoda.mind.memory.data.user_profile import UserProfile


# --- effective_skill_preferences ---


def test_effective_skill_preferences_empty_profile():
    prefs = ExecutionContextCore.effective_skill_preferences(
        UserProfile(), "search_web",
    )
    assert prefs == []


def test_effective_skill_preferences_only_canonical_search_web():
    profile = UserProfile(
        skill_preferences={"search_web": ["prefer Reuters", "avoid blogs"]},
    )
    assert ExecutionContextCore.effective_skill_preferences(
        profile, "search_web",
    ) == ["prefer Reuters", "avoid blogs"]


def test_effective_skill_preferences_only_legacy_web_search():
    profile = UserProfile(
        skill_preferences={"web_search": ["prefer BBC"]},
    )
    assert ExecutionContextCore.effective_skill_preferences(
        profile, "search_web",
    ) == ["prefer BBC"]


def test_effective_skill_preferences_dual_key_canonical_first_dedupe():
    profile = UserProfile(
        skill_preferences={
            "search_web": ["Prefer Reuters", "avoid blogs"],
            "web_search": ["prefer reuters", "use AP"],
        },
    )
    assert ExecutionContextCore.effective_skill_preferences(
        profile, "search_web",
    ) == ["Prefer Reuters", "avoid blogs", "use AP"]


def test_effective_skill_preferences_other_skill_exact_key_only():
    profile = UserProfile(
        skill_preferences={
            "schedule_message": ["short reminders"],
            "search_web": ["prefer Reuters"],
            "web_search": ["prefer BBC"],
        },
    )
    assert ExecutionContextCore.effective_skill_preferences(
        profile, "schedule_message",
    ) == ["short reminders"]
    assert ExecutionContextCore.effective_skill_preferences(
        profile, "missing_skill",
    ) == []


def test_effective_skill_preferences_does_not_mutate_profile():
    profile = UserProfile(
        skill_preferences={"web_search": ["prefer BBC"]},
    )
    original = dict(profile.skill_preferences)
    ExecutionContextCore.effective_skill_preferences(profile, "search_web")
    assert profile.skill_preferences == original


# --- normalize_request_constraints ---


def test_normalize_request_constraints_bare_host_and_url():
    raw = RequestConstraints(
        strict_source_domains=["AccuWeather.com", "https://www.reuters.com/world"],
        soft_source_domains=["HTTP://Weather.COM/path"],
    )
    out = ExecutionContextCore.normalize_request_constraints(raw)
    assert out.strict_source_domains == ["accuweather.com", "www.reuters.com"]
    assert out.soft_source_domains == ["weather.com"]


def test_normalize_request_constraints_strips_trailing_dns_dot_only():
    out = ExecutionContextCore.normalize_request_constraints(
        RequestConstraints(strict_source_domains=["example.com."]),
    )
    assert out.strict_source_domains == ["example.com"]


def test_normalize_request_constraints_strict_wins_over_soft_duplicate():
    out = ExecutionContextCore.normalize_request_constraints(
        RequestConstraints(
            strict_source_domains=["Example.COM"],
            soft_source_domains=["example.com", "news.org"],
        ),
    )
    assert out.strict_source_domains == ["example.com"]
    assert out.soft_source_domains == ["news.org"]


def test_normalize_request_constraints_case_insensitive_dedupe_stable_order():
    out = ExecutionContextCore.normalize_request_constraints(
        RequestConstraints(
            strict_source_domains=["a.com", "B.com", "a.COM", "c.com"],
        ),
    )
    assert out.strict_source_domains == ["a.com", "b.com", "c.com"]


@pytest.mark.parametrize(
    "bad",
    [
        "http://user:pass@evil.com",
        "*.example.com",
        ".example.com",
        "ftp://example.com",
        "127.0.0.1",
        "[::1]",
        "",
        "bad..label.com",
        "http://",
    ],
)
def test_normalize_request_constraints_rejects_invalid_hosts(bad: str):
    with pytest.raises(ValueError):
        ExecutionContextCore.normalize_request_constraints(
            RequestConstraints(strict_source_domains=[bad]),
        )


def test_normalize_host_preserves_www_and_subdomain():
    assert ExecutionContextCore.normalize_host("https://www.news.example.com:443/x") == (
        "www.news.example.com"
    )


# --- prepare_tool_requests ---


def _search(domains: list[str] | None = None) -> ToolCallRequest:
    args: dict = {"query": "forecast"}
    if domains is not None:
        args["include_domains"] = domains
    return ToolCallRequest(tool_name="web_search", arguments=args)


def test_prepare_tool_requests_injects_strict_include_domains():
    constraints = RequestConstraints(strict_source_domains=["accuweather.com"])
    prepared, issue = ExecutionContextCore.prepare_tool_requests(
        [_search()], constraints,
    )
    assert issue is None
    assert prepared[0].arguments["include_domains"] == ["accuweather.com"]


def test_prepare_tool_requests_accepts_set_equal_include_domains():
    constraints = RequestConstraints(
        strict_source_domains=["a.com", "b.com"],
    )
    prepared, issue = ExecutionContextCore.prepare_tool_requests(
        [_search(["b.com", "a.com"])], constraints,
    )
    assert issue is None
    assert set(prepared[0].arguments["include_domains"]) == {"a.com", "b.com"}


def test_prepare_tool_requests_rejects_broader_or_empty_include_domains():
    constraints = RequestConstraints(strict_source_domains=["a.com"])
    _, issue = ExecutionContextCore.prepare_tool_requests(
        [_search(["a.com", "b.com"])], constraints,
    )
    assert issue is not None
    assert issue.stage == AgentPhase.EXECUTION
    assert issue.category == ProtocolIssueCategory.INVALID_CONSTRAINT

    _, issue2 = ExecutionContextCore.prepare_tool_requests(
        [_search([])], constraints,
    )
    assert issue2 is not None
    assert issue2.category == ProtocolIssueCategory.INVALID_CONSTRAINT


def test_prepare_tool_requests_rejects_conflicting_include_domains():
    constraints = RequestConstraints(strict_source_domains=["a.com"])
    prepared, issue = ExecutionContextCore.prepare_tool_requests(
        [_search(["other.com"])], constraints,
    )
    assert prepared == []
    assert issue is not None
    assert issue.category == ProtocolIssueCategory.INVALID_CONSTRAINT


def test_prepare_tool_requests_soft_only_does_not_force_injection():
    constraints = RequestConstraints(soft_source_domains=["soft.com"])
    prepared, issue = ExecutionContextCore.prepare_tool_requests(
        [_search()], constraints,
    )
    assert issue is None
    assert "include_domains" not in prepared[0].arguments


def test_prepare_tool_requests_web_extract_under_allowed_host():
    constraints = RequestConstraints(strict_source_domains=["example.com"])
    ok = ToolCallRequest(
        tool_name="web_extract",
        arguments={"urls": ["https://sub.example.com/page"]},
    )
    prepared, issue = ExecutionContextCore.prepare_tool_requests([ok], constraints)
    assert issue is None
    assert prepared == [ok]

    bad = ToolCallRequest(
        tool_name="web_extract",
        arguments={"urls": ["https://other.com/page"]},
    )
    prepared2, issue2 = ExecutionContextCore.prepare_tool_requests([bad], constraints)
    assert prepared2 == []
    assert issue2 is not None
    assert issue2.category == ProtocolIssueCategory.INVALID_CONSTRAINT


def test_prepare_tool_requests_schedule_task_gets_injected_constraints():
    constraints = RequestConstraints(
        strict_source_domains=["a.com"],
        soft_source_domains=["b.com"],
    )
    req = ToolCallRequest(
        tool_name="schedule_task",
        arguments={
            "skill_name": "search_web",
            "distilled_task": "daily forecast",
            "request_constraints": {"strict_source_domains": ["evil.com"]},
        },
    )
    prepared, issue = ExecutionContextCore.prepare_tool_requests([req], constraints)
    assert issue is None
    assert prepared[0].arguments["request_constraints"] == {
        "strict_source_domains": ["a.com"],
        "soft_source_domains": ["b.com"],
    }


def test_prepare_tool_requests_repeated_calls_keep_equal_restriction():
    constraints = RequestConstraints(strict_source_domains=["a.com"])
    first, issue1 = ExecutionContextCore.prepare_tool_requests([_search()], constraints)
    second, issue2 = ExecutionContextCore.prepare_tool_requests(
        [_search(first[0].arguments["include_domains"])], constraints,
    )
    assert issue1 is None and issue2 is None
    assert second[0].arguments["include_domains"] == ["a.com"]


# --- canonicalize_profile_update_fields ---


def test_canonicalize_profile_only_legacy_write_to_search_web():
    fields = {
        "skill_preferences": {"web_search": ["prefer BBC"]},
    }
    out = ExecutionContextCore.canonicalize_profile_update_fields(fields)
    assert out == {"skill_preferences": {"search_web": ["prefer BBC"]}}


def test_canonicalize_profile_dual_key_merge():
    fields = {
        "skill_preferences_to_add": {
            "search_web": ["Prefer Reuters"],
            "web_search": ["prefer reuters", "use AP"],
            "schedule_message": ["short"],
        },
    }
    out = ExecutionContextCore.canonicalize_profile_update_fields(fields)
    assert out["skill_preferences_to_add"]["search_web"] == [
        "Prefer Reuters",
        "use AP",
    ]
    assert out["skill_preferences_to_add"]["schedule_message"] == ["short"]
    assert "web_search" not in out["skill_preferences_to_add"]


def test_canonicalize_profile_unrelated_keys_unchanged():
    fields = {"timezone": "Europe/Moscow", "location": "SPB"}
    assert ExecutionContextCore.canonicalize_profile_update_fields(fields) == fields
