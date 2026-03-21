from yoda.mind.agent.core.react_loop import ReactLoop
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
    SkillSummary(name="schedule_message", description="Schedule a reminder"),
    SkillSummary(name="web_search", description="Search the web"),
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


def test_build_context_selection_phase_includes_catalog():
    context = _make_context()
    messages = ReactLoop.build_context(context, TOOL_SCHEMAS, "2026-03-20 15:00 UTC")

    system_msg = messages[0]["content"]
    assert "schedule_message" in system_msg
    assert "web_search" in system_msg
    assert "Select the best skill" in system_msg


def test_build_context_execution_phase_includes_skill_and_tools():
    context = _make_context(active_skill=SKILL_SPEC)
    messages = ReactLoop.build_context(context, TOOL_SCHEMAS, "2026-03-20 15:00 UTC")

    system_msg = messages[0]["content"]
    assert "Active skill: schedule_message" in system_msg
    assert "reminder_text" in system_msg
    assert "Follow the active skill" in system_msg


def test_build_context_includes_profile_timezone():
    context = _make_context(active_skill=SKILL_SPEC)
    messages = ReactLoop.build_context(context, TOOL_SCHEMAS, "2026-03-20 15:00 UTC")

    system_msg = messages[0]["content"]
    assert "Europe/Moscow" in system_msg


def test_build_context_notes_missing_timezone():
    context = _make_context(
        active_skill=SKILL_SPEC,
        profile=UserProfile(),
    )
    messages = ReactLoop.build_context(context, TOOL_SCHEMAS, "2026-03-20 15:00 UTC")

    system_msg = messages[0]["content"]
    assert "no timezone or location on file" in system_msg


def test_build_context_includes_history():
    context = _make_context(
        active_skill=SKILL_SPEC,
        history=[ToolResult(tool_name="ask_user", output="Europe/Moscow", success=True)],
    )
    messages = ReactLoop.build_context(context, TOOL_SCHEMAS, "2026-03-20 15:00 UTC")

    history_msgs = [m for m in messages if "User answered:" in m["content"]]
    assert len(history_msgs) == 1
    assert "Europe/Moscow" in history_msgs[0]["content"]


def test_validate_decision_rejects_unknown_skill():
    context = _make_context()
    decision = Decision(selected_skill="nonexistent_skill")

    validated = ReactLoop.validate_decision(
        decision, context, {"schedule_message", "ask_user"})

    assert validated.final_answer is not None
    assert "Unknown skill" in validated.final_answer


def test_validate_decision_passes_valid_skill():
    context = _make_context()
    decision = Decision(selected_skill="schedule_message")

    validated = ReactLoop.validate_decision(
        decision, context, {"schedule_message", "ask_user"})

    assert validated.selected_skill == "schedule_message"
    assert validated.final_answer is None


def test_validate_decision_rejects_unknown_tool():
    context = _make_context(active_skill=SKILL_SPEC)
    decision = Decision(tool_calls=[
        ToolCallRequest(tool_name="nonexistent_tool", arguments={}),
    ])

    validated = ReactLoop.validate_decision(
        decision, context, {"schedule_message", "ask_user"})

    assert validated.final_answer is not None
    assert "Unknown tool" in validated.final_answer


def test_observe_increments_iteration_and_appends_history():
    context = _make_context(active_skill=SKILL_SPEC)
    results = [ToolResult(tool_name="schedule_message", output="OK", success=True)]

    new_context = ReactLoop.observe(context, results)

    assert new_context.iteration == 1
    assert len(new_context.history) == 1
    assert "schedule_message" in new_context.tools_used


def test_observe_does_not_mutate_original():
    context = _make_context(active_skill=SKILL_SPEC)
    results = [ToolResult(tool_name="schedule_message", output="OK", success=True)]

    new_context = ReactLoop.observe(context, results)

    assert context.iteration == 0
    assert len(context.history) == 0
    assert new_context is not context


def test_is_done_respects_max_iterations():
    context = _make_context(active_skill=SKILL_SPEC, iteration=3)
    assert ReactLoop.is_done(context) is True


def test_is_done_false_within_limit():
    context = _make_context(active_skill=SKILL_SPEC, iteration=2)
    assert ReactLoop.is_done(context) is False
