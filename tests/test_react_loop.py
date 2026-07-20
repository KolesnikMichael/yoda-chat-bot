from pydantic import ValidationError

from yoda.mind.agent.core.react_loop import (
    INFRA_TOOLS,
    SELECTION_INSTRUCTION,
    _LEGACY_SELECTION_INSTRUCTION,
    ReactLoop,
)
from yoda.mind.agent.data.agent_data import (
    AgentContext,
    AgentFailure,
    AgentPhase,
    ExecutionDecision,
    ProtocolIssue,
    ProtocolIssueCategory,
    RequestConstraints,
    SelectionDecision,
    SkillSpec,
    SkillSummary,
    ToolCallRequest,
    ToolResult,
)
from yoda.mind.memory.data.user_profile import UserProfile

CATALOG = [
    SkillSummary(
        name="schedule_message",
        description="Schedule a reminder",
        purpose="Deliver static reminder text later.",
        when_to_use=["Payload is known now."],
        do_not_use_when=["Needs fresh data at trigger time."],
        selection_examples=['"remind vitamins" -> use'],
    ),
    SkillSummary(
        name="web_search",
        description="Search the web",
        purpose="Fetch current external information.",
        when_to_use=["Needs current facts."],
        do_not_use_when=["Only static text later."],
        selection_examples=['"weather now" -> use'],
    ),
]

TOOL_SCHEMAS = [
    {"name": "schedule_message", "parameters": {"reminder_text": {"type": "string"}}, "required": ["reminder_text"]},
    {"name": "ask_user", "parameters": {"question": {"type": "string"}}, "required": ["question"]},
]

SKILL_SPEC = SkillSpec(
    name="schedule_message",
    description="Schedule a reminder",
    required_inputs={"reminder_text": "What to remind about"},
    tools=["schedule_message", "ask_user"],
    instructions="1. Call schedule_message.\n2. Confirm.",
    max_iterations=3,
)

AVAILABLE_SKILLS = {s.name for s in CATALOG}
AVAILABLE_TOOLS = {"schedule_message", "ask_user", "update_profile"}
LEGACY_COMBINED_SYSTEM_CONTENT = (
    "You are an executor agent. Your job is to complete tasks using "
    "available tools. Be precise, follow the skill workflow, and produce "
    "structured decisions.\n\n"
    "You MUST respond with a JSON object matching this schema:\n"
    '{"selected_skill":"skill_name or null",'
    '"distilled_task":"execution brief or null",'
    '"tool_calls":[],"final_answer":"answer text or null"}\n'
    "Phase 1 may call ask_user or update_profile before choosing a skill."
)


def _make_context(**overrides) -> AgentContext:
    defaults = dict(
        task="remind me in 30 minutes to call mom",
        profile=UserProfile(timezone="Europe/Moscow"),
        chat_id=42,
        catalog_summaries=CATALOG,
    )
    return AgentContext(**(defaults | overrides))


# --- SelectionDecision / ExecutionDecision extra_forbid ---

def test_SelectionDecision_rejects_extra_forbid_fields():
    try:
        SelectionDecision(
            mode="select_skill",
            selected_skill="schedule_message",
            distilled_task="remind vitamins",
            final_answer="nope",
        )
        assert False, "Expected ValidationError"
    except ValidationError:
        pass


def test_ExecutionDecision_rejects_extra_forbid_fields():
    try:
        ExecutionDecision(
            mode="finish",
            final_answer="done",
            selected_skill="schedule_message",
        )
        assert False, "Expected ValidationError"
    except ValidationError:
        pass


def test_SelectionDecision_constructs_valid_select_skill():
    d = SelectionDecision(
        mode="select_skill",
        selected_skill="schedule_message",
        distilled_task="remind vitamins",
    )
    assert d.mode == "select_skill"
    assert d.reason is None
    assert d.request_constraints == RequestConstraints()


def test_RequestConstraints_defaults_empty_lists():
    c = RequestConstraints()
    assert c.strict_source_domains == []
    assert c.soft_source_domains == []


def test_RequestConstraints_rejects_extra_forbid_fields():
    try:
        RequestConstraints(strict_source_domains=["a.com"], extra="nope")
        assert False, "Expected ValidationError"
    except ValidationError:
        pass


def test_SelectionDecision_accepts_request_constraints():
    d = SelectionDecision(
        mode="select_skill",
        selected_skill="search_web",
        distilled_task="forecast from accuweather only",
        request_constraints=RequestConstraints(
            strict_source_domains=["accuweather.com"],
            soft_source_domains=["weather.com"],
        ),
    )
    assert d.request_constraints.strict_source_domains == ["accuweather.com"]
    assert d.request_constraints.soft_source_domains == ["weather.com"]


def test_ProtocolIssueCategory_INVALID_CONSTRAINT_exists():
    assert ProtocolIssueCategory.INVALID_CONSTRAINT == "invalid_constraint"


def test_ExecutionDecision_constructs_valid_call_tools():
    d = ExecutionDecision(
        mode="call_tools",
        tool_calls=[ToolCallRequest(tool_name="ask_user", arguments={"question": "?"})],
    )
    assert d.mode == "call_tools"
    assert d.final_answer is None


# --- AgentContext / AgentFailure / protocol ---

def test_agent_context_defaults_phase_protocol_retry():
    ctx = _make_context()
    assert ctx.phase == AgentPhase.SELECTION
    assert ctx.selection_retry_used is False
    assert ctx.execution_retry_used is False
    assert ctx.protocol_version == 3
    assert ctx.request_constraints == RequestConstraints()


def test_agent_context_with_messages_preserves_protocol_fields():
    constraints = RequestConstraints(strict_source_domains=["example.com"])
    ctx = _make_context(
        phase=AgentPhase.EXECUTION,
        selection_retry_used=True,
        execution_retry_used=True,
        protocol_version=3,
        request_constraints=constraints,
    )
    new_ctx = ctx.with_messages([{"role": "user", "content": "x"}])
    assert new_ctx.phase == AgentPhase.EXECUTION
    assert new_ctx.selection_retry_used is True
    assert new_ctx.execution_retry_used is True
    assert new_ctx.protocol_version == 3
    assert new_ctx.request_constraints == constraints
    assert new_ctx.messages == [{"role": "user", "content": "x"}]


def test_AgentFailure_protocol_exhausted():
    failure = AgentFailure(
        stage=AgentPhase.SELECTION,
        category="protocol_exhausted",
        issue=ProtocolIssueCategory.MALFORMED_OUTPUT,
    )
    assert failure.stage == AgentPhase.SELECTION
    assert failure.category == "protocol_exhausted"


# --- build_system_message (execution-oriented) ---

def test_build_system_message_has_role_schema_and_profile():
    profile = UserProfile(timezone="Europe/Moscow")
    msg = ReactLoop.build_system_message(profile)

    assert msg["role"] == "system"
    content = msg["content"]
    assert "executor agent" in content
    assert "call_tools" in content or "final_answer" in content
    assert "Europe/Moscow" in content
    assert "selected_skill" not in content
    assert "UTC" not in content


def test_build_system_message_notes_missing_timezone():
    msg = ReactLoop.build_system_message(UserProfile())

    assert "no timezone or location on file" in msg["content"]


def test_build_selection_system_message_has_no_tools_or_ask_user():
    msg = ReactLoop.build_selection_system_message(UserProfile())
    content = msg["content"]
    assert "select_skill" in content
    assert "no_skill" in content
    assert "ask_user" not in content
    assert "tool_calls" not in content
    assert "final_answer" not in content


def test_build_execution_system_message_has_no_selection_fields():
    msg = ReactLoop.build_execution_system_message(UserProfile())
    content = msg["content"]
    assert "call_tools" in content
    assert "final_answer" in content
    assert "selected_skill" not in content
    assert "distilled_task" not in content


# --- build_context ---

def test_build_context_appends_time_after_messages():
    system = ReactLoop.build_execution_system_message(UserProfile(timezone="Europe/Moscow"))
    ctx = _make_context(messages=[
        system,
        {"role": "user", "content": "Task: test"},
        {"role": "assistant", "content": '{"reasoning": "ok"}'},
    ])
    result = ReactLoop.build_context(ctx, "2026-03-20 15:00 UTC")

    assert result[0] == system
    assert result[1] == {"role": "user", "content": "Task: test"}
    assert result[2]["role"] == "assistant"
    assert result[3]["role"] == "system"
    assert "2026-03-20 15:00 UTC" in result[3]["content"]
    assert len(result) == 4


# --- filter_tool_schemas ---

def test_filter_tool_schemas_includes_skill_and_infra_tools():
    skill = SkillSpec(
        name="s",
        description="d",
        required_inputs={},
        tools=["schedule_message"],
        instructions="x",
    )
    filtered = ReactLoop.filter_tool_schemas(TOOL_SCHEMAS, skill)

    names = {s["name"] for s in filtered}
    assert names == {"schedule_message", "ask_user"}
    assert names <= (set(skill.tools) | set(INFRA_TOOLS))


def test_filter_tool_schemas_excludes_tools_not_in_skill():
    extra = TOOL_SCHEMAS + [
        {"name": "other_tool", "parameters": {}, "required": []},
    ]
    filtered = ReactLoop.filter_tool_schemas(extra, SKILL_SPEC)
    names = {s["name"] for s in filtered}
    assert "other_tool" not in names


# --- selection control / input ---

def test_build_selection_control_message_role_and_markers():
    msg = ReactLoop.build_selection_control_message(CATALOG)

    assert msg["role"] == "system"
    content = msg["content"]
    assert "<skill_selection_control>" in content
    assert "</skill_selection_control>" in content
    assert "Catalog order has no semantic priority" in content
    assert "purpose:" in content
    assert "when_to_use:" in content
    assert "do_not_use_when:" in content
    assert "selection_examples:" in content
    assert "schedule_message" in content
    assert "web_search" in content
    assert "Schedule a reminder" not in content
    assert "Search the web" not in content
    assert "ask_user" not in content


def test_build_selection_control_message_name_sort_stable():
    reversed_catalog = list(reversed(CATALOG))
    forward = ReactLoop.build_selection_control_message(CATALOG)
    backward = ReactLoop.build_selection_control_message(reversed_catalog)
    assert forward["content"] == backward["content"]
    assert forward["content"].index("schedule_message") < forward["content"].index(
        "web_search"
    )


def test_build_selection_control_message_includes_private_skills():
    catalog = CATALOG + [
        SkillSummary(
            name="manage_user_data",
            description="Private",
            public=False,
            purpose="Manage stored data.",
            when_to_use=["Export or delete all data."],
            do_not_use_when=["Cancel a reminder."],
            selection_examples=['"forget me" -> use'],
        ),
    ]
    msg = ReactLoop.build_selection_control_message(catalog)
    assert "manage_user_data" in msg["content"]


def test_build_selection_control_message_empty_catalog():
    msg = ReactLoop.build_selection_control_message([])
    assert msg["role"] == "system"
    assert "No skills available." in msg["content"]


def test_build_selection_input_message_role_and_markers():
    msg = ReactLoop.build_selection_input_message("find weather")

    assert msg["role"] == "user"
    content = msg["content"]
    assert "<selection_input>" in content
    assert "<task>" in content
    assert "find weather" in content
    assert "<skill_selection_control>" not in content
    assert "Available skills" not in content
    assert "Select the best skill" not in content


def test_build_selection_input_message_includes_recent_conversation():
    recent = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    msg = ReactLoop.build_selection_input_message("find weather", recent)
    assert "<recent_conversation>" in msg["content"]
    assert "hi" in msg["content"]


def test_refresh_selection_messages_new_format_replaces_control():
    control = ReactLoop.build_selection_control_message(CATALOG)
    selection_input = ReactLoop.build_selection_input_message("old task")
    ctx = _make_context(messages=[
        {"role": "system", "content": "base"},
        control,
        selection_input,
        {"role": "assistant", "content": '{"reasoning":"clarify"}'},
        {"role": "user", "content": "User answered: Moscow"},
    ])
    refreshed_catalog = [
        SkillSummary(
            name="schedule_message",
            description="Schedule a reminder",
            purpose="UPDATED PURPOSE",
            when_to_use=["Updated trigger."],
            do_not_use_when=["Updated boundary."],
            selection_examples=['"updated" -> use'],
        ),
    ]
    new_ctx = ReactLoop.refresh_selection_messages(ctx, refreshed_catalog)
    assert "UPDATED PURPOSE" in new_ctx.messages[1]["content"]
    assert new_ctx.messages[2] == selection_input
    assert new_ctx.messages[3]["role"] == "assistant"
    assert new_ctx.messages[4]["content"] == "User answered: Moscow"
    assert new_ctx.catalog_summaries == refreshed_catalog


def test_refresh_selection_messages_new_format_ignores_markers_in_user_data():
    selection_input = ReactLoop.build_selection_input_message(
        "Explain <skill_selection_control> and <selection_input> literally."
    )
    ctx = _make_context(messages=[
        {"role": "system", "content": "base"},
        ReactLoop.build_selection_control_message(CATALOG),
        selection_input,
    ])

    new_ctx = ReactLoop.refresh_selection_messages(ctx, CATALOG)

    assert new_ctx.messages[2] == selection_input


def test_refresh_selection_messages_legacy_preserves_prefix_and_tail():
    legacy_user = {
        "role": "user",
        "content": (
            "Recent conversation:\nuser: earlier\n\n"
            "Task: remind vitamins\n\n"
            "Available skills:\n"
            "- schedule_message: Schedule a reminder\n"
            "- web_search: Search the web\n\n"
            f"{_LEGACY_SELECTION_INSTRUCTION}"
        ),
    }
    ctx = _make_context(messages=[
        {"role": "system", "content": "base"},
        legacy_user,
        {"role": "assistant", "content": '{"tool_calls":[]}'},
        {"role": "user", "content": "User answered: Europe/Moscow"},
    ])
    new_ctx = ReactLoop.refresh_selection_messages(ctx, CATALOG)
    assert new_ctx.messages[1]["role"] == "system"
    assert "<skill_selection_control>" in new_ctx.messages[1]["content"]
    assert new_ctx.messages[2]["role"] == "user"
    assert "<selection_input>" in new_ctx.messages[2]["content"]
    assert "remind vitamins" in new_ctx.messages[2]["content"]
    assert "Available skills:" not in new_ctx.messages[2]["content"]
    assert new_ctx.messages[3]["role"] == "assistant"
    assert new_ctx.messages[4]["content"] == "User answered: Europe/Moscow"


def test_refresh_selection_messages_legacy_preserves_delimiters_in_user_data():
    user_prefix = (
        "Task: Explain Available skills: and No skills available. literally, "
        "including <skill_selection_control> and <selection_input>."
    )
    legacy_user = {
        "role": "user",
        "content": (
            f"{user_prefix}\n\n"
            "Available skills:\n"
            "- schedule_message: Schedule a reminder\n"
            "- web_search: Search the web\n\n"
            f"{_LEGACY_SELECTION_INSTRUCTION}"
        ),
    }
    ctx = _make_context(messages=[
        {"role": "system", "content": "base"},
        legacy_user,
    ])

    new_ctx = ReactLoop.refresh_selection_messages(ctx, CATALOG)

    assert user_prefix in new_ctx.messages[2]["content"]


def test_refresh_selection_messages_unrecognized_raises():
    ctx = _make_context(messages=[{"role": "system", "content": "base only"}])
    try:
        ReactLoop.refresh_selection_messages(ctx, CATALOG)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "Unrecognized" in str(e)


# --- build_activation_message ---

def test_build_compact_execution_messages_order_and_content():
    profile = UserProfile(timezone="Europe/Moscow")
    activation = ReactLoop.build_activation_message(SKILL_SPEC, TOOL_SCHEMAS)
    msgs = ReactLoop.build_compact_execution_messages(
        profile,
        "Distilled brief.",
        SKILL_SPEC,
        activation,
        skill_preferences=["prefer short"],
        request_constraints=RequestConstraints(
            strict_source_domains=["example.com"],
            soft_source_domains=["fallback.example"],
        ),
    )

    assert len(msgs) == 3
    assert msgs[0]["role"] == "system"
    assert '<profile_data trust="untrusted">' in msgs[0]["content"]
    assert '"skill_preferences": ["prefer short"]' in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "<task>" in msgs[1]["content"]
    assert "Distilled brief." in msgs[1]["content"]
    assert '"strict_source_domains": ["example.com"]' in msgs[1]["content"]
    assert '"soft_source_domains": ["fallback.example"]' in msgs[1]["content"]
    assert "prefer short" not in msgs[1]["content"]
    assert msgs[2] == activation
    assert msgs[2]["role"] == "system"
    assert not any(m["role"] == "assistant" for m in msgs)
    assert "selected_skill" not in msgs[0]["content"]


def test_execution_profile_data_only_active_skill_preferences():
    profile = UserProfile(
        timezone="Europe/Moscow",
        skill_preferences={
            "search_web": ["prefer Reuters"],
            "schedule_message": ["short reminders"],
        },
    )
    activation = ReactLoop.build_activation_message(SKILL_SPEC, TOOL_SCHEMAS)
    msgs = ReactLoop.build_compact_execution_messages(
        profile,
        "remind vitamins",
        SKILL_SPEC,
        activation,
        skill_preferences=["short reminders"],
    )
    content = msgs[0]["content"]
    assert '"skill_name": "schedule_message"' in content
    assert '"skill_preferences": ["short reminders"]' in content
    assert "prefer Reuters" not in content
    assert "skill_preferences" not in ReactLoop.build_selection_system_message(
        profile,
    )["content"]


def test_execution_empty_preferences_and_constraints_render_explicit_lists():
    activation = ReactLoop.build_activation_message(SKILL_SPEC, TOOL_SCHEMAS)
    msgs = ReactLoop.build_compact_execution_messages(
        UserProfile(), "task", SKILL_SPEC, activation,
    )
    assert '"skill_preferences": []' in msgs[0]["content"]
    assert (
        '<request_constraints>{"strict_source_domains": [], '
        '"soft_source_domains": []}</request_constraints>'
    ) in msgs[1]["content"]


def test_selection_schema_mentions_request_constraints():
    content = ReactLoop.build_selection_system_message(UserProfile())["content"]
    assert "request_constraints" in content
    assert "strict_source_domains" in content
    assert "soft_source_domains" in content
    assert "skill_preferences" not in content


def test_selection_decision_missing_request_constraints_defaults_empty():
    d = SelectionDecision.model_validate({
        "mode": "select_skill",
        "selected_skill": "search_web",
        "distilled_task": "find news",
    })
    assert d.request_constraints == RequestConstraints()


def test_selection_decision_with_domains_parses():
    d = SelectionDecision.model_validate({
        "mode": "select_skill",
        "selected_skill": "search_web",
        "distilled_task": "forecast only from accuweather",
        "request_constraints": {
            "strict_source_domains": ["accuweather.com"],
            "soft_source_domains": [],
        },
    })
    assert d.request_constraints.strict_source_domains == ["accuweather.com"]


def test_build_activation_message_contains_skill_spec_and_tools():
    msg = ReactLoop.build_activation_message(SKILL_SPEC, TOOL_SCHEMAS)

    assert msg["role"] == "system"
    assert "schedule_message" in msg["content"]
    assert "Schedule a reminder" in msg["content"]
    assert "reminder_text" in msg["content"]
    assert "Call schedule_message" in msg["content"]
    assert "execute" in msg["content"].lower()
    assert "Available tools:" in msg["content"]
    assert "ask_user" in msg["content"]


# --- append_assistant ---

def test_append_assistant_adds_message():
    ctx = _make_context(messages=[
        {"role": "user", "content": "Task: test"},
    ])
    decision = SelectionDecision(
        mode="select_skill",
        selected_skill="schedule_message",
        distilled_task="remind mom",
        reasoning="selecting skill",
    )

    new_ctx = ReactLoop.append_assistant(ctx, decision)

    assert len(new_ctx.messages) == 2
    assert new_ctx.messages[1]["role"] == "assistant"
    assert "schedule_message" in new_ctx.messages[1]["content"]


def test_append_assistant_does_not_mutate_original():
    ctx = _make_context(messages=[
        {"role": "user", "content": "Task: test"},
    ])
    decision = ExecutionDecision(mode="finish", final_answer="done", reasoning="test")

    new_ctx = ReactLoop.append_assistant(ctx, decision)

    assert len(ctx.messages) == 1
    assert len(new_ctx.messages) == 2
    assert new_ctx is not ctx


# --- append_tool_results ---

def test_append_tool_results_adds_messages_and_increments():
    ctx = _make_context(active_skill=SKILL_SPEC, messages=[
        {"role": "user", "content": "Task: test"},
    ])
    results = [
        ToolResult(tool_name="schedule_message", output="OK", success=True),
    ]

    new_ctx = ReactLoop.append_tool_results(ctx, results)

    assert new_ctx.iteration == 1
    assert len(new_ctx.messages) == 2
    assert new_ctx.messages[1]["role"] == "system"
    assert "[schedule_message] (OK)" in new_ctx.messages[1]["content"]
    assert "schedule_message" in new_ctx.tools_used


def test_append_tool_results_preserves_retry_flags():
    ctx = _make_context(
        active_skill=SKILL_SPEC,
        selection_retry_used=True,
        execution_retry_used=True,
        phase=AgentPhase.EXECUTION,
    )
    results = [ToolResult(tool_name="schedule_message", output="OK", success=True)]

    new_ctx = ReactLoop.append_tool_results(ctx, results)

    assert new_ctx.selection_retry_used is True
    assert new_ctx.execution_retry_used is True
    assert new_ctx.phase == AgentPhase.EXECUTION
    assert new_ctx.protocol_version == 3
    assert new_ctx.request_constraints == RequestConstraints()
    ctx = _make_context(active_skill=SKILL_SPEC)
    results = [ToolResult(tool_name="schedule_message", output="OK", success=True)]

    new_ctx = ReactLoop.append_tool_results(ctx, results)

    assert ctx.iteration == 0
    assert len(ctx.messages) == 0
    assert new_ctx is not ctx


def test_append_tool_results_ask_user_format():
    ctx = _make_context(active_skill=SKILL_SPEC)
    results = [ToolResult(tool_name="ask_user", output="What timezone?", success=True)]

    new_ctx = ReactLoop.append_tool_results(ctx, results)

    assert "User was asked: What timezone?" in new_ctx.messages[0]["content"]


def test_append_tool_results_failed_tool():
    ctx = _make_context(active_skill=SKILL_SPEC)
    results = [ToolResult(tool_name="schedule_message", output="error", success=False)]

    new_ctx = ReactLoop.append_tool_results(ctx, results)

    assert "(FAILED)" in new_ctx.messages[0]["content"]


# --- validate_selection / validate_execution ---

def test_validate_selection_accepts_select_skill():
    decision = SelectionDecision(
        mode="select_skill",
        selected_skill="schedule_message",
        distilled_task="remind vitamins",
    )
    assert ReactLoop.validate_selection_decision(decision, AVAILABLE_SKILLS) is None


def test_validate_selection_accepts_no_skill():
    decision = SelectionDecision(mode="no_skill", reason="unsupported")
    assert ReactLoop.validate_selection_decision(decision, AVAILABLE_SKILLS) is None


def test_validate_selection_rejects_unknown_skill():
    decision = SelectionDecision(
        mode="select_skill",
        selected_skill="nonexistent_skill",
        distilled_task="x",
    )
    issue = ReactLoop.validate_selection_decision(decision, AVAILABLE_SKILLS)
    assert issue is not None
    assert issue.category == ProtocolIssueCategory.UNKNOWN_SKILL
    assert issue.stage == AgentPhase.SELECTION


def test_validate_selection_rejects_blank_distilled_task():
    decision = SelectionDecision(
        mode="select_skill",
        selected_skill="schedule_message",
        distilled_task="   ",
    )
    issue = ReactLoop.validate_selection_decision(decision, AVAILABLE_SKILLS)
    assert issue is not None
    assert issue.category == ProtocolIssueCategory.INVALID_MODE


def test_validate_selection_rejects_reason_on_select_skill():
    decision = SelectionDecision(
        mode="select_skill",
        selected_skill="schedule_message",
        distilled_task="ok",
        reason="unsupported",
    )
    issue = ReactLoop.validate_selection_decision(decision, AVAILABLE_SKILLS)
    assert issue is not None
    assert issue.category == ProtocolIssueCategory.INVALID_MODE


def test_validate_selection_rejects_skill_on_no_skill():
    decision = SelectionDecision(
        mode="no_skill",
        reason="unsupported",
        selected_skill="schedule_message",
    )
    issue = ReactLoop.validate_selection_decision(decision, AVAILABLE_SKILLS)
    assert issue is not None
    assert issue.category == ProtocolIssueCategory.INVALID_MODE


def test_validate_execution_accepts_call_tools():
    decision = ExecutionDecision(
        mode="call_tools",
        tool_calls=[ToolCallRequest(tool_name="ask_user", arguments={"question": "?"})],
    )
    assert ReactLoop.validate_execution_decision(decision, AVAILABLE_TOOLS) is None


def test_validate_execution_accepts_finish():
    decision = ExecutionDecision(mode="finish", final_answer="Done.")
    assert ReactLoop.validate_execution_decision(decision, AVAILABLE_TOOLS) is None


def test_validate_execution_rejects_unknown_tool():
    decision = ExecutionDecision(
        mode="call_tools",
        tool_calls=[ToolCallRequest(tool_name="nonexistent_tool", arguments={})],
    )
    issue = ReactLoop.validate_execution_decision(decision, AVAILABLE_TOOLS)
    assert issue is not None
    assert issue.category == ProtocolIssueCategory.UNKNOWN_TOOL


def test_validate_execution_rejects_tools_with_final_answer():
    decision = ExecutionDecision(
        mode="call_tools",
        tool_calls=[ToolCallRequest(tool_name="ask_user", arguments={"question": "?"})],
        final_answer="also answer",
    )
    issue = ReactLoop.validate_execution_decision(decision, AVAILABLE_TOOLS)
    assert issue is not None
    assert issue.category == ProtocolIssueCategory.INVALID_MODE


def test_validate_execution_rejects_finish_with_tools():
    decision = ExecutionDecision(
        mode="finish",
        final_answer="done",
        tool_calls=[ToolCallRequest(tool_name="ask_user", arguments={"question": "?"})],
    )
    issue = ReactLoop.validate_execution_decision(decision, AVAILABLE_TOOLS)
    assert issue is not None
    assert issue.category == ProtocolIssueCategory.INVALID_MODE


def test_validate_execution_rejects_blank_final_answer():
    decision = ExecutionDecision(mode="finish", final_answer="  ")
    issue = ReactLoop.validate_execution_decision(decision, AVAILABLE_TOOLS)
    assert issue is not None
    assert issue.category == ProtocolIssueCategory.INVALID_MODE


# --- append_correction ---

def test_append_correction_selection_sets_retry_and_system_message():
    ctx = _make_context(messages=[{"role": "user", "content": "secret user task XYZ"}])
    issue = ProtocolIssue(
        stage=AgentPhase.SELECTION,
        category=ProtocolIssueCategory.MALFORMED_OUTPUT,
    )
    new_ctx = ReactLoop.append_correction(ctx, issue)

    assert new_ctx.selection_retry_used is True
    assert new_ctx.execution_retry_used is False
    assert new_ctx.messages[-1]["role"] == "system"
    content = new_ctx.messages[-1]["content"]
    assert "SelectionDecision" in content
    assert "secret user task XYZ" not in content


def test_append_correction_second_call_does_not_add_budget():
    ctx = _make_context(selection_retry_used=True, messages=[])
    issue = ProtocolIssue(
        stage=AgentPhase.SELECTION,
        category=ProtocolIssueCategory.INVALID_MODE,
    )
    new_ctx = ReactLoop.append_correction(ctx, issue)
    assert new_ctx.selection_retry_used is True
    assert new_ctx.messages == []


def test_append_correction_execution_template():
    ctx = _make_context(phase=AgentPhase.EXECUTION, task="do not leak THIS_TASK")
    issue = ProtocolIssue(
        stage=AgentPhase.EXECUTION,
        category=ProtocolIssueCategory.UNKNOWN_TOOL,
    )
    new_ctx = ReactLoop.append_correction(ctx, issue)
    assert new_ctx.execution_retry_used is True
    content = new_ctx.messages[-1]["content"]
    assert "ExecutionDecision" in content
    assert "THIS_TASK" not in content


# --- upgrade_legacy_protocol ---

def test_upgrade_legacy_pre_selection_refreshes_seed():
    control = ReactLoop.build_selection_control_message(CATALOG)
    selection_input = ReactLoop.build_selection_input_message("task")
    legacy_system = {
        "role": "system",
        "content": LEGACY_COMBINED_SYSTEM_CONTENT,
    }
    ctx = _make_context(
        protocol_version=1,
        phase=AgentPhase.SELECTION,
        active_skill=None,
        messages=[
            legacy_system,
            control,
            selection_input,
            {"role": "assistant", "content": '{"selected_skill":"schedule_message"}'},
        ],
    )
    upgraded = ReactLoop.upgrade_legacy_protocol(ctx, CATALOG)
    assert upgraded.protocol_version == 3
    assert upgraded.phase == AgentPhase.SELECTION
    assert "skill-selection agent" in upgraded.messages[0]["content"]
    assert "tool_calls" not in upgraded.messages[0]["content"]
    assert "ask_user" not in upgraded.messages[0]["content"]
    assert "<skill_selection_control>" in upgraded.messages[1]["content"]
    assert upgraded.messages[3]["content"] == '{"selected_skill":"schedule_message"}'
    assert upgraded.request_constraints == RequestConstraints()


def test_upgrade_legacy_active_execution_replaces_system():
    old_system = {
        "role": "system",
        "content": LEGACY_COMBINED_SYSTEM_CONTENT,
    }
    tool_history = {"role": "system", "content": "[web_search] (OK) results"}
    ctx = _make_context(
        protocol_version=1,
        active_skill=SKILL_SPEC,
        phase=AgentPhase.EXECUTION,
        messages=[
            old_system,
            {"role": "user", "content": "Task:\nbrief"},
            ReactLoop.build_activation_message(SKILL_SPEC, TOOL_SCHEMAS),
            {"role": "assistant", "content": '{"tool_calls":[]}'},
            tool_history,
        ],
        request_constraints=RequestConstraints(
            strict_source_domains=["example.com"],
        ),
    )
    upgraded = ReactLoop.upgrade_legacy_protocol(
        ctx,
        CATALOG,
        skill_preferences=["short"],
    )
    assert upgraded.protocol_version == 3
    assert upgraded.phase == AgentPhase.EXECUTION
    assert "selected_skill" not in upgraded.messages[0]["content"]
    assert "call_tools" in upgraded.messages[0]["content"]
    assert '<profile_data trust="untrusted">' in upgraded.messages[0]["content"]
    assert "<task>" in upgraded.messages[1]["content"]
    assert '"strict_source_domains": ["example.com"]' in upgraded.messages[1]["content"]
    assert upgraded.messages[-2]["content"] == '{"tool_calls":[]}'
    assert upgraded.messages[-1] == tool_history
    assert upgraded.active_skill == SKILL_SPEC
    assert upgraded.request_constraints.strict_source_domains == ["example.com"]


def test_append_correction_INVALID_CONSTRAINT_is_sanitized():
    ctx = _make_context(
        phase=AgentPhase.EXECUTION,
        request_constraints=RequestConstraints(
            strict_source_domains=["secret-domain.example"],
        ),
    )
    issue = ProtocolIssue(
        stage=AgentPhase.EXECUTION,
        category=ProtocolIssueCategory.INVALID_CONSTRAINT,
    )
    new_ctx = ReactLoop.append_correction(ctx, issue)
    content = new_ctx.messages[-1]["content"]
    assert "ExecutionDecision" in content
    assert "secret-domain.example" not in content
    assert "source constraints" in content


# --- is_done ---

def test_is_done_respects_max_iterations():
    ctx = _make_context(active_skill=SKILL_SPEC, iteration=3)
    assert ReactLoop.is_done(ctx) is True


def test_is_done_false_within_limit():
    ctx = _make_context(active_skill=SKILL_SPEC, iteration=2)
    assert ReactLoop.is_done(ctx) is False


# silence unused import warning for SELECTION_INSTRUCTION in some linters
assert SELECTION_INSTRUCTION
