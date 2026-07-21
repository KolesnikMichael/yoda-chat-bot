"""Regenerate corpus-v1.json for TASK-020."""

from __future__ import annotations

import json
from pathlib import Path

NA_CHAT = {
    "selection": {"kind": "not_applicable", "reason": "chat_route"},
    "planning": {"kind": "not_applicable", "reason": "chat_route"},
    "execution": {"kind": "not_applicable", "reason": "chat_route"},
    "delivery": {"kind": "not_applicable", "reason": "chat_route"},
}

PROFILE = {"timezone": "Europe/Moscow", "location": "Saint Petersburg"}

BASE_PROHIBITIONS = [
    "internal_details",
    "changed_certainty",
    "unproved_side_effect",
]
IMMEDIATE_PROHIBITIONS = ["uncreated_job", *BASE_PROHIBITIONS]
STATIC_JOB_PROHIBITIONS = [
    "live_recomputation",
    "future_result",
    *BASE_PROHIBITIONS,
]
DYNAMIC_JOB_PROHIBITIONS = ["future_result", *BASE_PROHIBITIONS]
CLARIFICATION_PROHIBITIONS = [
    "unproved_side_effect",
    "internal_details",
    "changed_certainty",
]


def exact_delivery_claims(expected: dict) -> dict:
    delivery = expected.get("delivery")
    if not isinstance(delivery, dict) or delivery.get("kind") != "delivery":
        return expected
    delivery = dict(delivery)
    allowed = delivery.get("allowed_claims", [])
    if delivery.get("status") == "clarification":
        prohibited = CLARIFICATION_PROHIBITIONS
    elif delivery.get("status") == "failure":
        prohibited = BASE_PROHIBITIONS
    elif allowed == ["stored_text_scheduled"]:
        prohibited = STATIC_JOB_PROHIBITIONS
    elif allowed == ["dynamic_operation_scheduled"]:
        prohibited = DYNAMIC_JOB_PROHIBITIONS
    elif allowed == ["stored_text_delivered"]:
        prohibited = ["live_recomputation", *BASE_PROHIBITIONS]
    elif allowed == ["picture_sent"]:
        prohibited = BASE_PROHIBITIONS
    else:
        prohibited = IMMEDIATE_PROHIBITIONS
    delivery["prohibited_claims"] = prohibited
    return {**expected, "delivery": delivery}


def turn(
    tid: str,
    event: str,
    text: str,
    *,
    model_responses: list[dict],
    tool_results: list[dict] | None = None,
    expected: dict,
    profile: dict | None = None,
    recent: list[dict] | None = None,
    skill_name: str | None = None,
    distilled: str | None = None,
    constraints: dict | None = None,
) -> dict:
    turn_input: dict = {"text": text}
    if recent:
        turn_input["recent_messages"] = recent
    if constraints:
        turn_input["request_constraints"] = constraints
    if skill_name:
        turn_input["skill_name"] = skill_name
    if distilled:
        turn_input["distilled_task"] = distilled
    return {
        "id": tid,
        "event": event,
        "input": turn_input,
        "fixed_now_utc": "2026-07-20T08:00:00+00:00",
        "profile": profile or PROFILE,
        "model_responses": model_responses,
        "tool_results": tool_results or [],
        "expected": exact_delivery_claims(expected),
    }


def chat_case(case_id: str, language: str, text: str) -> dict:
    return {
        "id": case_id,
        "language": language,
        "purpose": f"{language} chat",
        "turns": [
            turn(
                "t1",
                "message",
                text,
                model_responses=[
                    {"stage": "intent", "raw": json.dumps({"intent": "chat"})},
                ],
                expected={
                    "intent": {"kind": "intent", "route": "chat"},
                    **NA_CHAT,
                },
            ),
        ],
    }


def search_immediate(
    case_id: str,
    language: str,
    text: str,
    task: str,
    query: str,
    *,
    recent: list[dict] | None = None,
    required_task_fragments: list[str] | None = None,
) -> dict:
    return {
        "id": case_id,
        "language": language,
        "purpose": f"{language} immediate web search",
        "turns": [
            turn(
                "t1",
                "message",
                text,
                model_responses=[
                    {"stage": "intent", "raw": json.dumps({"intent": "agent_task"})},
                    {
                        "stage": "selection",
                        "raw": json.dumps(
                            {
                                "mode": "select_skill",
                                "selected_skill": "search_web",
                                "distilled_task": task,
                            },
                        ),
                    },
                    {
                        "stage": "planning",
                        "raw": json.dumps(
                            {
                                "mode": "call_tools",
                                "tool_calls": [
                                    {
                                        "tool_name": "web_search",
                                        "arguments": {"query": query},
                                    },
                                ],
                            },
                        ),
                    },
                    {
                        "stage": "planning",
                        "raw": json.dumps(
                            {"mode": "finish", "final_answer": "Sunny."},
                        ),
                    },
                ],
                tool_results=[
                    {
                        "tool_name": "web_search",
                        "output": "Sunny 20C",
                        "success": True,
                    },
                ],
                recent=recent,
                expected={
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "select_skill",
                        "selected_skill": "search_web",
                        **(
                            {
                                "distilled_task": {
                                    "required_fragments": required_task_fragments,
                                },
                            }
                            if required_task_fragments
                            else {}
                        ),
                    },
                    "planning": {
                        "kind": "planning",
                        "accepted_modes": ["call_tools", "finish"],
                        "tool_batches": [
                            {
                                "matching": "ordered",
                                "calls": [
                                    {
                                        "tool_name": "web_search",
                                        "arguments": {"query": query},
                                    },
                                ],
                            },
                        ],
                    },
                    "execution": {
                        "kind": "execution",
                        "result": "success",
                        "operation": "retrieve_information",
                        "result_kind": "information",
                    },
                    "delivery": {
                        "kind": "delivery",
                        "status": "success",
                        "allowed_claims": ["operation_completed"],
                    },
                },
            ),
        ],
    }


def schedule_static_message(case_id: str, language: str, text: str) -> dict:
    return {
        "id": case_id,
        "language": language,
        "purpose": f"{language} recurring static reminder",
        "turns": [
            turn(
                "t1",
                "message",
                text,
                model_responses=[
                    {"stage": "intent", "raw": json.dumps({"intent": "agent_task"})},
                    {
                        "stage": "selection",
                        "raw": json.dumps(
                            {
                                "mode": "select_skill",
                                "selected_skill": "schedule_message",
                                "distilled_task": text,
                            },
                        ),
                    },
                    {
                        "stage": "planning",
                        "raw": json.dumps(
                            {
                                "mode": "call_tools",
                                "tool_calls": [
                                    {
                                        "tool_name": "schedule_message",
                                        "arguments": {
                                                "reminder_text": "Take vitamins",
                                            "cron": "0 9 * * *",
                                            "timezone": "Europe/Moscow",
                                        },
                                    },
                                ],
                            },
                        ),
                    },
                ],
                tool_results=[
                    {
                        "tool_name": "schedule_message",
                        "output": "Scheduled",
                        "success": True,
                        "terminal_facts": {
                            "result_kind": "scheduled_job",
                            "summary": "Daily vitamins reminder scheduled",
                            "job_kind": "message",
                            "schedule": "0 9 * * * Europe/Moscow",
                        },
                    },
                ],
                expected={
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "select_skill",
                        "selected_skill": "schedule_message",
                    },
                    "planning": {
                        "kind": "planning",
                        "accepted_modes": ["call_tools"],
                        "tool_batches": [
                            {
                                "matching": "ordered",
                                "calls": [
                                    {
                                        "tool_name": "schedule_message",
                                        "arguments": {
                                            "reminder_text": "Take vitamins",
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                    "execution": {
                        "kind": "execution",
                        "result": "success",
                        "operation": "schedule_work",
                        "result_kind": "scheduled_job",
                        "job_kind": "message",
                    },
                    "delivery": {
                        "kind": "delivery",
                        "status": "success",
                        "allowed_claims": ["stored_text_scheduled"],
                        "prohibited_claims": ["live_recomputation", "future_result"],
                    },
                },
            ),
        ],
    }


def skill_with_finish(
    case_id: str,
    language: str,
    text: str,
    *,
    skill: str,
    tool_name: str,
    tool_args: dict,
    tool_output: str,
    execution: dict,
    delivery: dict,
) -> dict:
    return {
        "id": case_id,
        "language": language,
        "purpose": f"{language} {skill}",
        "turns": [
            turn(
                "t1",
                "message",
                text,
                model_responses=[
                    {"stage": "intent", "raw": json.dumps({"intent": "agent_task"})},
                    {
                        "stage": "selection",
                        "raw": json.dumps(
                            {
                                "mode": "select_skill",
                                "selected_skill": skill,
                                "distilled_task": text,
                            },
                        ),
                    },
                    {
                        "stage": "planning",
                        "raw": json.dumps(
                            {
                                "mode": "call_tools",
                                "tool_calls": [
                                    {"tool_name": tool_name, "arguments": tool_args},
                                ],
                            },
                        ),
                    },
                    {
                        "stage": "planning",
                        "raw": json.dumps(
                            {"mode": "finish", "final_answer": tool_output},
                        ),
                    },
                ],
                tool_results=[
                    {
                        "tool_name": tool_name,
                        "output": tool_output,
                        "success": True,
                    },
                ],
                expected={
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "select_skill",
                        "selected_skill": skill,
                    },
                    "planning": {
                        "kind": "planning",
                        "accepted_modes": ["call_tools", "finish"],
                        "tool_batches": [
                            {
                                "matching": "ordered",
                                "calls": [{"tool_name": tool_name, "arguments": tool_args}],
                            },
                        ],
                    },
                    "execution": execution,
                    "delivery": delivery,
                },
            ),
        ],
    }


def skill_terminal_case(
    case_id: str,
    language: str,
    text: str,
    *,
    skill: str,
    tool_name: str,
    tool_args: dict,
    tool_output: str,
    terminal_facts: dict | None = None,
    execution: dict,
    delivery: dict,
) -> dict:
    return {
        "id": case_id,
        "language": language,
        "purpose": f"{language} {skill}",
        "turns": [
            turn(
                "t1",
                "message",
                text,
                model_responses=[
                    {"stage": "intent", "raw": json.dumps({"intent": "agent_task"})},
                    {
                        "stage": "selection",
                        "raw": json.dumps(
                            {
                                "mode": "select_skill",
                                "selected_skill": skill,
                                "distilled_task": text,
                            },
                        ),
                    },
                    {
                        "stage": "planning",
                        "raw": json.dumps(
                            {
                                "mode": "call_tools",
                                "tool_calls": [
                                    {"tool_name": tool_name, "arguments": tool_args},
                                ],
                            },
                        ),
                    },
                ],
                tool_results=[
                    {
                        "tool_name": tool_name,
                        "output": tool_output,
                        "success": True,
                        **({"terminal_facts": terminal_facts} if terminal_facts else {}),
                    },
                ],
                expected={
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "select_skill",
                        "selected_skill": skill,
                    },
                    "planning": {
                        "kind": "planning",
                        "accepted_modes": ["call_tools"],
                        "tool_batches": [
                            {
                                "matching": "ordered",
                                "calls": [{"tool_name": tool_name, "arguments": tool_args}],
                            },
                        ],
                    },
                    "execution": execution,
                    "delivery": delivery,
                },
            ),
        ],
    }


def recorded(stage: str, payload: dict | str) -> dict:
    return {
        "stage": stage,
        "raw": payload if isinstance(payload, str) else json.dumps(payload),
    }


def routing_case(
    case_id: str,
    language: str,
    purpose: str,
    turns: list[dict],
) -> dict:
    return {
        "id": case_id,
        "language": language,
        "purpose": purpose,
        "turns": turns,
    }


def no_skill_case() -> dict:
    return routing_case(
        "en-selection-no-skill",
        "en",
        "unsupported request produces typed no-skill outcome",
        [
            turn(
                "t1",
                "message",
                "Teleport me to Mars",
                model_responses=[
                    recorded("intent", {"intent": "agent_task"}),
                    recorded(
                        "selection",
                        {"mode": "no_skill", "reason": "unsupported"},
                    ),
                ],
                expected={
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "no_skill",
                    },
                    "planning": {
                        "kind": "not_applicable",
                        "reason": "upstream_stop",
                    },
                    "execution": {
                        "kind": "execution",
                        "result": "failure",
                        "operation": "requested_work",
                        "failure_category": "unsupported",
                        "next_step": "state_capability_boundary",
                    },
                    "delivery": {
                        "kind": "delivery",
                        "status": "failure",
                        "allowed_claims": ["safe_limitation"],
                        "source_text": {
                            "prohibited_fragments": ["schema", "provider", "tool"],
                        },
                    },
                },
            ),
        ],
    )


def selection_corrected_case() -> dict:
    return routing_case(
        "en-selection-protocol-corrected",
        "en",
        "malformed selection recovers on one bounded correction",
        [
            turn(
                "t1",
                "message",
                "Find today's weather in Berlin",
                model_responses=[
                    recorded("intent", {"intent": "agent_task"}),
                    recorded("selection", "{bad-json"),
                    recorded(
                        "selection",
                        {
                            "mode": "select_skill",
                            "selected_skill": "search_web",
                            "distilled_task": "Find today's weather in Berlin.",
                        },
                    ),
                    recorded(
                        "planning",
                        {
                            "mode": "call_tools",
                            "tool_calls": [
                                {
                                    "tool_name": "web_search",
                                    "arguments": {"query": "Berlin weather today"},
                                },
                            ],
                        },
                    ),
                    recorded(
                        "planning",
                        {"mode": "finish", "final_answer": "Sunny in Berlin."},
                    ),
                ],
                tool_results=[
                    {
                        "tool_name": "web_search",
                        "output": "Berlin: sunny 18C",
                        "success": True,
                    },
                ],
                expected={
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "select_skill",
                        "selected_skill": "search_web",
                        "distilled_task": {
                            "required_fragments": ["Berlin", "weather"],
                        },
                        "recovery": "corrected",
                    },
                    "planning": {
                        "kind": "planning",
                        "accepted_modes": ["call_tools", "finish"],
                        "tool_batches": [
                            {
                                "matching": "ordered",
                                "calls": [
                                    {
                                        "tool_name": "web_search",
                                        "arguments": {"query": "Berlin"},
                                    },
                                ],
                            },
                        ],
                    },
                    "execution": {
                        "kind": "execution",
                        "result": "success",
                        "operation": "retrieve_information",
                        "result_kind": "information",
                    },
                    "delivery": {
                        "kind": "delivery",
                        "status": "success",
                        "allowed_claims": ["operation_completed"],
                    },
                },
            ),
        ],
    )


def selection_exhausted_case() -> dict:
    return routing_case(
        "ru-selection-protocol-exhausted",
        "ru",
        "malformed selection exhausts one bounded correction",
        [
            turn(
                "t1",
                "message",
                "Найди свежие новости",
                model_responses=[
                    recorded("intent", {"intent": "agent_task"}),
                    recorded("selection", "{bad-json"),
                    recorded("selection", "{still-bad"),
                ],
                expected={
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "protocol_exhausted",
                        "recovery": "exhausted",
                    },
                    "planning": {
                        "kind": "not_applicable",
                        "reason": "upstream_stop",
                    },
                    "execution": {
                        "kind": "execution",
                        "result": "failure",
                        "operation": "requested_work",
                        "failure_category": "transient",
                        "next_step": "try_later",
                    },
                    "delivery": {
                        "kind": "delivery",
                        "status": "failure",
                        "allowed_claims": ["safe_limitation"],
                        "source_text": {
                            "prohibited_fragments": ["schema", "provider", "tool"],
                        },
                    },
                },
            ),
        ],
    )


def strict_preference_recovery_case() -> dict:
    constraints = {
        "strict_source_domains": ["accuweather.com"],
        "soft_source_domains": [],
    }
    return routing_case(
        "en-strict-constraint-overrides-preference",
        "en",
        "strict source survives invalid preferred-domain plan correction",
        [
            turn(
                "t1",
                "message",
                "Use only AccuWeather for today's Paris weather",
                profile={
                    **PROFILE,
                    "skill_preferences": {"search_web": ["example.com"]},
                },
                model_responses=[
                    recorded("intent", {"intent": "agent_task"}),
                    recorded(
                        "selection",
                        {
                            "mode": "select_skill",
                            "selected_skill": "search_web",
                            "distilled_task": (
                                "Find today's Paris weather using only AccuWeather."
                            ),
                            "request_constraints": constraints,
                        },
                    ),
                    recorded(
                        "planning",
                        {
                            "mode": "call_tools",
                            "tool_calls": [
                                {
                                    "tool_name": "web_search",
                                    "arguments": {
                                        "query": "Paris weather today",
                                        "include_domains": ["example.com"],
                                    },
                                },
                            ],
                        },
                    ),
                    recorded(
                        "planning",
                        {
                            "mode": "call_tools",
                            "tool_calls": [
                                {
                                    "tool_name": "web_search",
                                    "arguments": {"query": "Paris weather today"},
                                },
                            ],
                        },
                    ),
                    recorded(
                        "planning",
                        {
                            "mode": "finish",
                            "final_answer": "Paris weather retrieved.",
                        },
                    ),
                ],
                tool_results=[
                    {
                        "tool_name": "web_search",
                        "output": "Paris 24 C",
                        "success": True,
                    },
                ],
                expected={
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "select_skill",
                        "selected_skill": "search_web",
                        "distilled_task": {
                            "required_fragments": ["Paris", "AccuWeather"],
                        },
                        "request_constraints": constraints,
                    },
                    "planning": {
                        "kind": "planning",
                        "accepted_modes": ["call_tools", "finish"],
                        "recovery": "corrected",
                        "tool_batches": [
                            {
                                "matching": "ordered",
                                "calls": [
                                    {
                                        "tool_name": "web_search",
                                        "arguments": {
                                            "include_domains": ["accuweather.com"],
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                    "execution": {
                        "kind": "execution",
                        "result": "success",
                        "operation": "retrieve_information",
                        "result_kind": "information",
                    },
                    "delivery": {
                        "kind": "delivery",
                        "status": "success",
                        "allowed_claims": ["operation_completed"],
                    },
                },
            ),
        ],
    )


def execution_exhausted_case() -> dict:
    return routing_case(
        "ru-execution-protocol-exhausted",
        "ru",
        "malformed execution exhausts one bounded correction",
        [
            turn(
                "t1",
                "message",
                "Найди курс евро",
                model_responses=[
                    recorded("intent", {"intent": "agent_task"}),
                    recorded(
                        "selection",
                        {
                            "mode": "select_skill",
                            "selected_skill": "search_web",
                            "distilled_task": "Найти текущий курс евро.",
                        },
                    ),
                    recorded("planning", "{bad-json"),
                    recorded("planning", "{still-bad"),
                ],
                expected={
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "select_skill",
                        "selected_skill": "search_web",
                    },
                    "planning": {
                        "kind": "planning",
                        "accepted_modes": ["fail"],
                        "recovery": "exhausted",
                    },
                    "execution": {
                        "kind": "execution",
                        "result": "failure",
                        "operation": "retrieve_information",
                        "failure_category": "transient",
                        "next_step": "try_later",
                    },
                    "delivery": {
                        "kind": "delivery",
                        "status": "failure",
                        "allowed_claims": ["safe_limitation"],
                        "source_text": {
                            "prohibited_fragments": ["schema", "provider", "tool"],
                        },
                    },
                },
            ),
        ],
    )


def execution_unsupported_case() -> dict:
    return routing_case(
        "en-execution-unsupported",
        "en",
        "accepted execution fail maps to safe unsupported outcome",
        [
            turn(
                "t1",
                "message",
                "Find a private account password",
                model_responses=[
                    recorded("intent", {"intent": "agent_task"}),
                    recorded(
                        "selection",
                        {
                            "mode": "select_skill",
                            "selected_skill": "search_web",
                            "distilled_task": "Find a private account password.",
                        },
                    ),
                    recorded(
                        "planning",
                        {"mode": "fail", "failure_reason": "unsupported"},
                    ),
                ],
                expected={
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "select_skill",
                        "selected_skill": "search_web",
                    },
                    "planning": {
                        "kind": "planning",
                        "accepted_modes": ["fail"],
                    },
                    "execution": {
                        "kind": "execution",
                        "result": "failure",
                        "operation": "retrieve_information",
                        "failure_category": "unsupported",
                        "next_step": "state_capability_boundary",
                    },
                    "delivery": {
                        "kind": "delivery",
                        "status": "failure",
                        "allowed_claims": ["safe_limitation"],
                        "source_text": {
                            "prohibited_fragments": ["schema", "provider", "tool"],
                        },
                    },
                },
            ),
        ],
    )


def delayed_dynamic_case() -> dict:
    return routing_case(
        "en-delayed-dynamic-weather-check",
        "en",
        "delayed reminder performs fresh information task",
        [
            turn(
                "t1",
                "message",
                "In 30 minutes check the current weather in Oslo",
                model_responses=[
                    recorded("intent", {"intent": "agent_task"}),
                    recorded(
                        "selection",
                        {
                            "mode": "select_skill",
                            "selected_skill": "search_web",
                            "distilled_task": (
                                "In 30 minutes check current weather in Oslo."
                            ),
                        },
                    ),
                    recorded(
                        "planning",
                        {
                            "mode": "call_tools",
                            "tool_calls": [
                                {
                                    "tool_name": "schedule_task",
                                    "arguments": {
                                        "skill_name": "search_web",
                                        "distilled_task": (
                                            "Check current weather in Oslo."
                                        ),
                                        "description": "Oslo weather check",
                                        "delay_minutes": 30,
                                    },
                                },
                            ],
                        },
                    ),
                ],
                tool_results=[
                    {
                        "tool_name": "schedule_task",
                        "output": "Scheduled",
                        "success": True,
                        "terminal_facts": {
                            "result_kind": "scheduled_job",
                            "summary": "Oslo weather check scheduled",
                            "job_kind": "task",
                            "scheduled_skill_name": "search_web",
                            "schedule": "in 30 minutes",
                        },
                    },
                ],
                expected={
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "select_skill",
                        "selected_skill": "search_web",
                        "distilled_task": {
                            "required_fragments": ["30 minutes", "Oslo"],
                        },
                    },
                    "planning": {
                        "kind": "planning",
                        "accepted_modes": ["call_tools"],
                        "tool_batches": [
                            {
                                "matching": "ordered",
                                "calls": [
                                    {
                                        "tool_name": "schedule_task",
                                        "arguments": {
                                            "skill_name": "search_web",
                                            "delay_minutes": 30,
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                    "execution": {
                        "kind": "execution",
                        "result": "success",
                        "operation": "schedule_work",
                        "result_kind": "scheduled_job",
                        "job_kind": "task",
                        "scheduled_operation": "retrieve_information",
                        "schedule": {
                            "required_fragments": ["30 minutes"],
                        },
                    },
                    "delivery": {
                        "kind": "delivery",
                        "status": "success",
                        "allowed_claims": ["dynamic_operation_scheduled"],
                    },
                },
            ),
        ],
    )


def relative_static_case() -> dict:
    return routing_case(
        "ru-relative-static-reminder",
        "ru",
        "relative static reminder requires no timezone clarification",
        [
            turn(
                "t1",
                "message",
                "Через 15 минут напомни выключить духовку",
                profile={},
                model_responses=[
                    recorded("intent", {"intent": "agent_task"}),
                    recorded(
                        "selection",
                        {
                            "mode": "select_skill",
                            "selected_skill": "schedule_message",
                            "distilled_task": (
                                "Через 15 минут напомнить выключить духовку."
                            ),
                        },
                    ),
                    recorded(
                        "planning",
                        {
                            "mode": "call_tools",
                            "tool_calls": [
                                {
                                    "tool_name": "schedule_message",
                                    "arguments": {
                                        "reminder_text": "Выключить духовку",
                                        "delay_minutes": 15,
                                    },
                                },
                            ],
                        },
                    ),
                ],
                tool_results=[
                    {
                        "tool_name": "schedule_message",
                        "output": "Scheduled",
                        "success": True,
                        "terminal_facts": {
                            "result_kind": "scheduled_job",
                            "summary": "Oven reminder scheduled",
                            "job_kind": "message",
                            "schedule": "in 15 minutes",
                        },
                    },
                ],
                expected={
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "select_skill",
                        "selected_skill": "schedule_message",
                        "distilled_task": {
                            "required_fragments": ["15 минут", "духовку"],
                        },
                    },
                    "planning": {
                        "kind": "planning",
                        "accepted_modes": ["call_tools"],
                        "tool_batches": [
                            {
                                "matching": "ordered",
                                "calls": [
                                    {
                                        "tool_name": "schedule_message",
                                        "arguments": {
                                            "reminder_text": "духовку",
                                            "delay_minutes": 15,
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                    "execution": {
                        "kind": "execution",
                        "result": "success",
                        "operation": "schedule_work",
                        "result_kind": "scheduled_job",
                        "job_kind": "message",
                        "schedule": {
                            "required_fragments": ["15 minutes"],
                        },
                    },
                    "delivery": {
                        "kind": "delivery",
                        "status": "success",
                        "allowed_claims": ["stored_text_scheduled"],
                    },
                },
            ),
        ],
    )


def main() -> None:
    cases: list[dict] = [
        chat_case("en-intent-chat-greeting", "en", "Hello!"),
        chat_case("ru-intent-chat-greeting", "ru", "Привет!"),
        {
            "id": "en-intent-malformed-fallback",
            "language": "en",
            "purpose": "malformed intent falls back to chat",
            "turns": [
                turn(
                    "t1",
                    "message",
                    "Do something",
                    model_responses=[{"stage": "intent", "raw": "{bad-json"}],
                    expected={
                        "intent": {"kind": "intent", "route": "rejected_fallback_chat"},
                        **NA_CHAT,
                    },
                ),
            ],
        },
        {
            "id": "ru-intent-malformed-fallback",
            "language": "ru",
            "purpose": "malformed intent ru",
            "turns": [
                turn(
                    "t1",
                    "message",
                    "Сделай что-нибудь",
                    model_responses=[{"stage": "intent", "raw": "{bad-json"}],
                    expected={
                        "intent": {"kind": "intent", "route": "rejected_fallback_chat"},
                        **NA_CHAT,
                    },
                ),
            ],
        },
        search_immediate("en-search-immediate", "en", "What is the weather?", "Find weather.", "weather"),
        search_immediate("ru-search-immediate", "ru", "Какая погода?", "Узнать погоду.", "погода"),
        search_immediate(
            "en-search-refinement",
            "en",
            "And tomorrow?",
            "Find tomorrow's weather in Berlin.",
            "Berlin weather tomorrow",
            recent=[
                {"role": "user", "content": "What is the weather in Berlin?"},
                {"role": "assistant", "content": "It is sunny today."},
            ],
            required_task_fragments=["tomorrow", "Berlin"],
        ),
        search_immediate(
            "ru-search-refinement",
            "ru",
            "А завтра?",
            "Узнать погоду в Москве завтра.",
            "погода в Москве завтра",
            recent=[
                {"role": "user", "content": "Какая погода в Москве?"},
                {"role": "assistant", "content": "Сегодня солнечно."},
            ],
            required_task_fragments=["завтра", "Москве"],
        ),
        schedule_static_message("en-schedule-static-message", "en", "Remind me every morning to take vitamins"),
        schedule_static_message("ru-schedule-static-message", "ru", "Напоминай каждое утро принять витамины"),
        skill_with_finish(
            "en-skill-manage_jobs",
            "en",
            "List my scheduled jobs",
            skill="manage_jobs",
            tool_name="list_jobs",
            tool_args={},
            tool_output='[{"id":"job-1"}]',
            execution={
                "kind": "execution",
                "result": "success",
                "operation": "manage_scheduled_jobs",
                "result_kind": "job_state",
            },
            delivery={
                "kind": "delivery",
                "status": "success",
                "allowed_claims": ["operation_completed"],
            },
        ),
        skill_with_finish(
            "ru-skill-manage_jobs",
            "ru",
            "Покажи мои запланированные задачи",
            skill="manage_jobs",
            tool_name="list_jobs",
            tool_args={},
            tool_output="[]",
            execution={
                "kind": "execution",
                "result": "success",
                "operation": "manage_scheduled_jobs",
                "result_kind": "job_state",
            },
            delivery={
                "kind": "delivery",
                "status": "success",
                "allowed_claims": ["operation_completed"],
            },
        ),
        skill_with_finish(
            "en-skill-manage_user_data",
            "en",
            "What do you remember about me?",
            skill="manage_user_data",
            tool_name="get_user_data",
            tool_args={},
            tool_output="timezone=Europe/Moscow",
            execution={
                "kind": "execution",
                "result": "success",
                "operation": "manage_user_data",
                "result_kind": "user_data",
            },
            delivery={
                "kind": "delivery",
                "status": "success",
                "allowed_claims": ["operation_completed"],
            },
        ),
        skill_with_finish(
            "ru-skill-manage_user_data",
            "ru",
            "Что ты знаешь обо мне?",
            skill="manage_user_data",
            tool_name="get_user_data",
            tool_args={},
            tool_output="timezone=Europe/Moscow",
            execution={
                "kind": "execution",
                "result": "success",
                "operation": "manage_user_data",
                "result_kind": "user_data",
            },
            delivery={
                "kind": "delivery",
                "status": "success",
                "allowed_claims": ["operation_completed"],
            },
        ),
        skill_terminal_case(
            "en-skill-create_picture",
            "en",
            "Draw a sunset over the lake",
            skill="create_picture",
            tool_name="send_picture",
            tool_args={
                "file_path": "/tmp/synthetic.png",
                "summary_for_chat": "A sunset over a lake",
            },
            tool_output="sent",
            terminal_facts={
                "result_kind": "picture_sent",
                "summary": "Picture sent",
            },
            execution={
                "kind": "execution",
                "result": "success",
                "operation": "create_picture",
                "result_kind": "picture_sent",
            },
            delivery={
                "kind": "delivery",
                "status": "success",
                "allowed_claims": ["picture_sent"],
            },
        ),
        skill_terminal_case(
            "ru-skill-create_picture",
            "ru",
            "Нарисуй закат над озером",
            skill="create_picture",
            tool_name="send_picture",
            tool_args={
                "file_path": "/tmp/synthetic.png",
                "summary_for_chat": "Закат над озером",
            },
            tool_output="sent",
            terminal_facts={
                "result_kind": "picture_sent",
                "summary": "Картинка отправлена",
            },
            execution={
                "kind": "execution",
                "result": "success",
                "operation": "create_picture",
                "result_kind": "picture_sent",
            },
            delivery={
                "kind": "delivery",
                "status": "success",
                "allowed_claims": ["picture_sent"],
            },
        ),
        {
            "id": "en-clarification-suspend-resume",
            "language": "en",
            "purpose": "ask_user clarification suspend and resume",
            "turns": [
                turn(
                    "t1",
                    "message",
                    "Schedule a reminder",
                    model_responses=[
                        {"stage": "intent", "raw": json.dumps({"intent": "agent_task"})},
                        {
                            "stage": "selection",
                            "raw": json.dumps(
                                {
                                    "mode": "select_skill",
                                    "selected_skill": "schedule_message",
                                    "distilled_task": "Schedule a reminder",
                                },
                            ),
                        },
                        {
                            "stage": "planning",
                            "raw": json.dumps(
                                {
                                    "mode": "call_tools",
                                    "tool_calls": [
                                        {
                                            "tool_name": "ask_user",
                                            "arguments": {
                                                "question": "What time should I remind you?",
                                            },
                                        },
                                    ],
                                },
                            ),
                        },
                    ],
                    tool_results=[
                        {
                            "tool_name": "ask_user",
                            "output": "What time should I remind you?",
                            "success": True,
                            "suspend": True,
                        },
                    ],
                    expected={
                        "intent": {"kind": "intent", "route": "agent_task"},
                        "selection": {
                            "kind": "selection",
                            "mode": "select_skill",
                            "selected_skill": "schedule_message",
                        },
                        "planning": {
                            "kind": "planning",
                            "accepted_modes": ["call_tools"],
                            "tool_batches": [
                                {
                                    "matching": "ordered",
                                    "calls": [
                                        {
                                            "tool_name": "ask_user",
                                            "arguments": {"question": "What time"},
                                        },
                                    ],
                                },
                            ],
                        },
                        "execution": {
                            "kind": "execution",
                            "result": "clarification",
                        },
                        "delivery": {
                            "kind": "delivery",
                            "status": "clarification",
                            "prohibited_claims": ["unproved_side_effect"],
                        },
                    },
                ),
                turn(
                    "t2",
                    "resume",
                    "At 9am every day",
                    model_responses=[
                        {
                            "stage": "planning",
                            "raw": json.dumps(
                                {
                                    "mode": "call_tools",
                                    "tool_calls": [
                                        {
                                            "tool_name": "schedule_message",
                                            "arguments": {
                                                "reminder_text": "Reminder",
                                                "cron": "0 9 * * *",
                                                "timezone": "Europe/Moscow",
                                            },
                                        },
                                    ],
                                },
                            ),
                        },
                    ],
                    tool_results=[
                        {
                            "tool_name": "schedule_message",
                            "output": "Scheduled",
                            "success": True,
                            "terminal_facts": {
                                "result_kind": "scheduled_job",
                                "summary": "Reminder scheduled",
                                "job_kind": "message",
                                "schedule": "0 9 * * * Europe/Moscow",
                            },
                        },
                    ],
                    expected={
                        "intent": {"kind": "intent", "route": "agent_resume"},
                        "selection": {
                            "kind": "not_applicable",
                            "reason": "resume_bypass",
                        },
                        "planning": {
                            "kind": "planning",
                            "accepted_modes": ["call_tools"],
                            "tool_batches": [
                                {
                                    "matching": "ordered",
                                    "calls": [
                                        {
                                            "tool_name": "schedule_message",
                                            "arguments": {
                                                "reminder_text": "Reminder",
                                            },
                                        },
                                    ],
                                },
                            ],
                        },
                        "execution": {
                            "kind": "execution",
                            "result": "success",
                            "operation": "schedule_work",
                            "result_kind": "scheduled_job",
                            "job_kind": "message",
                        },
                        "delivery": {
                            "kind": "delivery",
                            "status": "success",
                            "allowed_claims": ["stored_text_scheduled"],
                        },
                    },
                ),
            ],
        },
        no_skill_case(),
        selection_corrected_case(),
        selection_exhausted_case(),
        strict_preference_recovery_case(),
        execution_exhausted_case(),
        execution_unsupported_case(),
        delayed_dynamic_case(),
        relative_static_case(),
        {
            "id": "july-20-recurring-spb-weather-accuweather",
            "language": "ru",
            "purpose": "July 20 synthetic recurring AccuWeather weather task",
            "turns": [
                turn(
                    "t1",
                    "message",
                    "Каждое утро в 08:00 присылай прогноз погоды в Санкт-Петербурге только с AccuWeather",
                    model_responses=[
                        {"stage": "intent", "raw": json.dumps({"intent": "agent_task"})},
                        {
                            "stage": "selection",
                            "raw": json.dumps(
                                {
                                    "mode": "select_skill",
                                    "selected_skill": "search_web",
                                    "distilled_task": (
                                        "Каждое утро в 08:00 получать прогноз погоды "
                                        "в Санкт-Петербурге только с AccuWeather."
                                    ),
                                    "request_constraints": {
                                        "strict_source_domains": ["accuweather.com"],
                                        "soft_source_domains": [],
                                    },
                                },
                            ),
                        },
                        {
                            "stage": "planning",
                            "raw": json.dumps(
                                {
                                    "mode": "call_tools",
                                    "tool_calls": [
                                        {
                                            "tool_name": "schedule_task",
                                            "arguments": {
                                                "skill_name": "search_web",
                                                "distilled_task": (
                                                    "Прогноз погоды в Санкт-Петербурге "
                                                    "с AccuWeather"
                                                ),
                                                "description": "Утренний прогноз",
                                                "cron": "0 8 * * *",
                                                "timezone": "Europe/Moscow",
                                            },
                                        },
                                    ],
                                },
                            ),
                        },
                    ],
                    tool_results=[
                        {
                            "tool_name": "schedule_task",
                            "output": "Scheduled",
                            "success": True,
                            "terminal_facts": {
                                "result_kind": "scheduled_job",
                                "summary": "Recurring weather lookup scheduled",
                                "job_kind": "task",
                                "scheduled_skill_name": "search_web",
                                "schedule": "0 8 * * * Europe/Moscow",
                            },
                        },
                    ],
                    expected={
                        "intent": {"kind": "intent", "route": "agent_task"},
                        "selection": {
                            "kind": "selection",
                            "mode": "select_skill",
                            "selected_skill": "search_web",
                            "distilled_task": {
                                "required_fragments": [
                                    "08:00",
                                    "Санкт-Петербурге",
                                    "AccuWeather",
                                ],
                            },
                            "request_constraints": {
                                "strict_source_domains": ["accuweather.com"],
                                "soft_source_domains": [],
                            },
                        },
                        "planning": {
                            "kind": "planning",
                            "accepted_modes": ["call_tools"],
                            "tool_batches": [
                                {
                                    "matching": "ordered",
                                    "calls": [
                                        {
                                            "tool_name": "schedule_task",
                                            "arguments": {
                                                "skill_name": "search_web",
                                                "distilled_task": "Санкт-Петербурге",
                                                "cron": "0 8 * * *",
                                                "timezone": "Europe/Moscow",
                                                "request_constraints": {
                                                    "strict_source_domains": [
                                                        "accuweather.com",
                                                    ],
                                                },
                                            },
                                        },
                                    ],
                                },
                            ],
                        },
                        "execution": {
                            "kind": "execution",
                            "result": "success",
                            "operation": "schedule_work",
                            "result_kind": "scheduled_job",
                            "job_kind": "task",
                            "scheduled_operation": "retrieve_information",
                            "schedule": {
                                "required_fragments": [
                                    "0 8 * * *",
                                    "Europe/Moscow",
                                ],
                            },
                        },
                        "delivery": {
                            "kind": "delivery",
                            "status": "success",
                            "allowed_claims": ["dynamic_operation_scheduled"],
                        },
                    },
                ),
                turn(
                    "t2",
                    "scheduled_task",
                    "Прогноз погоды в Санкт-Петербурге с AccuWeather",
                    skill_name="search_web",
                    distilled="Прогноз погоды в Санкт-Петербурге с AccuWeather",
                    constraints={
                        "strict_source_domains": ["accuweather.com"],
                        "soft_source_domains": [],
                    },
                    model_responses=[
                        recorded(
                            "planning",
                            {
                                "mode": "call_tools",
                                "tool_calls": [
                                    {
                                        "tool_name": "web_search",
                                        "arguments": {
                                            "query": "погода Санкт-Петербург",
                                        },
                                    },
                                ],
                            },
                        ),
                        recorded(
                            "planning",
                            {
                                "mode": "call_tools",
                                "tool_calls": [
                                    {
                                        "tool_name": "web_search",
                                        "arguments": {
                                            "query": "погода Санкт-Петербург сегодня",
                                            "include_domains": [
                                                "accuweather.com",
                                            ],
                                        },
                                    },
                                ],
                            },
                        ),
                        recorded(
                            "planning",
                            {
                                "mode": "finish",
                                "final_answer": "В Санкт-Петербурге 18 C.",
                            },
                        ),
                    ],
                    tool_results=[
                        {
                            "tool_name": "web_search",
                            "output": "No results",
                            "success": True,
                        },
                        {
                            "tool_name": "web_search",
                            "output": "Saint Petersburg weather: 18 C",
                            "success": True,
                        },
                    ],
                    expected={
                        "intent": {
                            "kind": "not_applicable",
                            "reason": "scheduled_bypass",
                        },
                        "selection": {
                            "kind": "not_applicable",
                            "reason": "scheduled_bypass",
                        },
                        "planning": {
                            "kind": "planning",
                            "accepted_modes": ["call_tools", "finish"],
                            "tool_batches": [
                                {
                                    "matching": "ordered",
                                    "calls": [
                                        {
                                            "tool_name": "web_search",
                                            "arguments": {
                                                "include_domains": [
                                                    "accuweather.com",
                                                ],
                                            },
                                        },
                                    ],
                                },
                                {
                                    "matching": "ordered",
                                    "calls": [
                                        {
                                            "tool_name": "web_search",
                                            "arguments": {
                                                "include_domains": [
                                                    "accuweather.com",
                                                ],
                                            },
                                        },
                                    ],
                                },
                            ],
                        },
                        "execution": {
                            "kind": "execution",
                            "result": "success",
                            "operation": "retrieve_information",
                            "result_kind": "information",
                        },
                        "delivery": {
                            "kind": "delivery",
                            "status": "success",
                            "allowed_claims": ["operation_completed"],
                        },
                    },
                ),
            ],
        },
    ]

    corpus = {"schema_version": 1, "corpus_version": "1.1.1", "cases": cases}
    out = Path(__file__).with_name("corpus-v1.json")
    out.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(cases)} cases to {out}")


if __name__ == "__main__":
    main()
