from yoda.mind.agent.core.react_loop import (
    INFRA_TOOLS,
    SELECTION_INSTRUCTION,
    ReactLoop,
)
from yoda.mind.agent.data.agent_data import (
    AgentContext,
    Decision,
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


def _make_context(**overrides) -> AgentContext:
    defaults = dict(
        task="remind me in 30 minutes to call mom",
        profile=UserProfile(timezone="Europe/Moscow"),
        chat_id=42,
        catalog_summaries=CATALOG,
    )
    return AgentContext(**(defaults | overrides))


# --- build_system_message ---

def test_build_system_message_has_role_schema_and_profile():
    profile = UserProfile(timezone="Europe/Moscow")
    msg = ReactLoop.build_system_message(profile)

    assert msg["role"] == "system"
    content = msg["content"]
    assert "executor agent" in content
    assert "selected_skill" in content
    assert "Europe/Moscow" in content
    assert "schedule_message" not in content
    assert "UTC" not in content


def test_build_system_message_notes_missing_timezone():
    msg = ReactLoop.build_system_message(UserProfile())

    assert "no timezone or location on file" in msg["content"]


# --- build_context ---

def test_build_context_appends_time_after_messages():
    system = ReactLoop.build_system_message(UserProfile(timezone="Europe/Moscow"))
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
            f"{SELECTION_INSTRUCTION}"
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
            f"{SELECTION_INSTRUCTION}"
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
        profile, "Distilled brief.", SKILL_SPEC, activation)

    assert len(msgs) == 3
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "Task:\nDistilled brief."
    assert msgs[2] == activation
    assert msgs[2]["role"] == "system"
    assert not any(m["role"] == "assistant" for m in msgs)


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
    decision = Decision(
        selected_skill="schedule_message",
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
    decision = Decision(reasoning="test")

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


def test_append_tool_results_does_not_mutate_original():
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


# --- validate_decision ---

def test_validate_decision_rejects_unknown_skill():
    ctx = _make_context(active_skill=None)
    decision = Decision(selected_skill="nonexistent_skill")

    validated = ReactLoop.validate_decision(
        decision, ctx, {"schedule_message", "ask_user"})

    assert validated.final_answer is not None
    assert "Unknown skill" in validated.final_answer


def test_validate_decision_phase1_rejects_skill_and_final_together():
    ctx = _make_context(active_skill=None)
    decision = Decision(selected_skill="schedule_message", final_answer="no")

    validated = ReactLoop.validate_decision(
        decision, ctx, {"schedule_message", "ask_user"})

    assert validated.final_answer is not None
    assert "exactly one" in validated.final_answer


def test_validate_decision_phase1_rejects_non_infra_tool():
    ctx = _make_context(active_skill=None)
    decision = Decision(tool_calls=[
        ToolCallRequest(tool_name="web_search", arguments={"query": "q"}),
    ])

    validated = ReactLoop.validate_decision(
        decision, ctx, {"ask_user", "web_search"})

    assert validated.final_answer is not None
    assert "Phase 1 only allows" in validated.final_answer


def test_validate_decision_phase1_allows_ask_user_only():
    ctx = _make_context(active_skill=None)
    decision = Decision(tool_calls=[
        ToolCallRequest(tool_name="ask_user", arguments={"question": "?"}),
    ])

    validated = ReactLoop.validate_decision(
        decision, ctx, {"ask_user", "web_search"})

    assert validated.tool_calls
    assert validated.final_answer is None


def test_validate_decision_passes_valid_skill():
    ctx = _make_context(active_skill=None)
    decision = Decision(selected_skill="schedule_message")

    validated = ReactLoop.validate_decision(
        decision, ctx, {"schedule_message", "ask_user"})

    assert validated.selected_skill == "schedule_message"
    assert validated.final_answer is None


def test_validate_decision_execution_strips_stray_phase1_fields():
    ctx = _make_context(active_skill=SKILL_SPEC)
    decision = Decision(
        distilled_task="should be stripped",
        selected_skill="schedule_message",
        tool_calls=[
            ToolCallRequest(
                tool_name="schedule_message",
                arguments={"reminder_text": "x"},
            ),
        ],
    )

    validated = ReactLoop.validate_decision(
        decision, ctx, {"schedule_message", "ask_user"})

    assert validated.distilled_task is None
    assert validated.selected_skill is None
    assert validated.tool_calls


def test_validate_decision_rejects_unknown_tool():
    ctx = _make_context(active_skill=SKILL_SPEC)
    decision = Decision(tool_calls=[
        ToolCallRequest(tool_name="nonexistent_tool", arguments={}),
    ])

    validated = ReactLoop.validate_decision(
        decision, ctx, {"schedule_message", "ask_user"})

    assert validated.final_answer is not None
    assert "Unknown tool" in validated.final_answer


# --- is_done ---

def test_is_done_respects_max_iterations():
    ctx = _make_context(active_skill=SKILL_SPEC, iteration=3)
    assert ReactLoop.is_done(ctx) is True


def test_is_done_false_within_limit():
    ctx = _make_context(active_skill=SKILL_SPEC, iteration=2)
    assert ReactLoop.is_done(ctx) is False
