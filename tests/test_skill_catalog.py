from pathlib import Path

from yoda.mind.agent.data.agent_data import SkillSummary
from yoda.mind.agent.skills.catalog import SkillCatalog

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "skills"


def test_skill_summary_selection_contract_fields():
    summary = SkillSummary(
        name="example",
        description="Public description.",
        public=True,
        purpose="Do the example thing.",
        when_to_use=["Positive trigger."],
        do_not_use_when=["Negative boundary."],
        selection_examples=['"Do it" -> use'],
    )
    assert summary.purpose == "Do the example thing."
    assert summary.when_to_use == ["Positive trigger."]
    assert summary.do_not_use_when == ["Negative boundary."]
    assert summary.selection_examples == ['"Do it" -> use']


def test_skill_summary_defaults_for_legacy_decode():
    summary = SkillSummary(name="legacy", description="Old summary.")
    assert summary.purpose == ""
    assert summary.when_to_use == []
    assert summary.do_not_use_when == []
    assert summary.selection_examples == []


def test_load_catalog_finds_all_specs():
    catalog = SkillCatalog.load_catalog(FIXTURES_DIR)

    names = {s.name for s in catalog}
    assert "test_skill" in names
    assert "no_tools_skill" in names


def test_load_catalog_has_descriptions():
    catalog = SkillCatalog.load_catalog(FIXTURES_DIR)

    test_skill = next(s for s in catalog if s.name == "test_skill")
    assert test_skill.description == "A test skill for unit tests."


def test_load_skill_returns_full_spec():
    spec = SkillCatalog.load_skill(FIXTURES_DIR, "test_skill")

    assert spec.name == "test_skill"
    assert spec.tools == ["web_search", "ask_user"]
    assert spec.required_inputs == {"query": "The search query"}
    assert spec.max_iterations == 3
    assert "Search for the query" in spec.instructions


def test_load_skill_not_found_raises():
    try:
        SkillCatalog.load_skill(FIXTURES_DIR, "nonexistent")
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "nonexistent" in str(e)


def test_validate_tools_reports_unknown():
    catalog = SkillCatalog.load_catalog(FIXTURES_DIR)
    warnings = SkillCatalog.validate_tools(
        catalog, FIXTURES_DIR, available_tools={"ask_user"})

    assert len(warnings) == 1
    assert "web_search" in warnings[0]


def test_validate_tools_no_warnings_when_all_present():
    catalog = SkillCatalog.load_catalog(FIXTURES_DIR)
    warnings = SkillCatalog.validate_tools(
        catalog, FIXTURES_DIR, available_tools={"web_search", "ask_user"})

    assert len(warnings) == 0


def test_load_catalog_from_nonexistent_dir():
    catalog = SkillCatalog.load_catalog(Path("/nonexistent/path"))
    assert catalog == []


def test_load_catalog_reads_public_field():
    catalog = SkillCatalog.load_catalog(FIXTURES_DIR)

    private = next(s for s in catalog if s.name == "private_skill")
    assert private.public is False

    test = next(s for s in catalog if s.name == "test_skill")
    assert test.public is True


def test_public_summaries_filters_private():
    catalog = SkillCatalog.load_catalog(FIXTURES_DIR)

    public = SkillCatalog.public_summaries(catalog)
    names = {s.name for s in public}
    assert "test_skill" in names
    assert "no_tools_skill" in names
    assert "private_skill" not in names


def test_public_summaries_empty_catalog():
    assert SkillCatalog.public_summaries([]) == []


def test_load_catalog_loads_selection_metadata():
    catalog = SkillCatalog.load_catalog(FIXTURES_DIR)
    test_skill = next(s for s in catalog if s.name == "test_skill")
    assert test_skill.purpose
    assert test_skill.when_to_use
    assert test_skill.do_not_use_when
    assert test_skill.selection_examples


def _write_spec(specs_dir: Path, stem: str, frontmatter: str) -> None:
    specs_dir.mkdir(parents=True, exist_ok=True)
    (specs_dir / f"{stem}.md").write_text(
        f"---\n{frontmatter}\n---\n# Body\n",
        encoding="utf-8",
    )


_VALID_SELECTION = """
purpose: Valid purpose.
when_to_use:
  - A positive trigger.
do_not_use_when:
  - A negative boundary.
selection_examples:
  - '"example" -> use'
""".strip()


def test_validate_selection_metadata_missing_purpose(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    _write_spec(
        skills_dir / "specs",
        "broken",
        f"name: broken\ndescription: x\n"
        f"when_to_use:\n  - a\ndo_not_use_when:\n  - b\n"
        f"selection_examples:\n  - c\n",
    )
    try:
        SkillCatalog.load_catalog(skills_dir)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "broken" in str(e)
        assert "purpose" in str(e)


def test_validate_selection_metadata_empty_list(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    _write_spec(
        skills_dir / "specs",
        "broken",
        "name: broken\ndescription: x\npurpose: Valid purpose.\n"
        "when_to_use: []\n"
        "do_not_use_when:\n  - A negative boundary.\n"
        "selection_examples:\n  - '\"example\" -> use'\n",
    )
    try:
        SkillCatalog.load_catalog(skills_dir)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "broken" in str(e)
        assert "when_to_use" in str(e)


def test_validate_selection_metadata_blank_list_member(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    _write_spec(
        skills_dir / "specs",
        "broken",
        "name: broken\ndescription: x\npurpose: Valid purpose.\n"
        "when_to_use:\n  - ' '\n"
        "do_not_use_when:\n  - A negative boundary.\n"
        "selection_examples:\n  - '\"example\" -> use'\n",
    )
    try:
        SkillCatalog.load_catalog(skills_dir)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "broken" in str(e)
        assert "when_to_use" in str(e)


def test_validate_selection_metadata_wrong_container_type(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    _write_spec(
        skills_dir / "specs",
        "broken",
        "name: broken\ndescription: x\npurpose: Valid purpose.\n"
        "when_to_use: not-a-list\n"
        "do_not_use_when:\n  - A negative boundary.\n"
        "selection_examples:\n  - '\"example\" -> use'\n",
    )
    try:
        SkillCatalog.load_catalog(skills_dir)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "broken" in str(e)
        assert "when_to_use" in str(e)


def test_load_catalog_missing_name_raises(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    _write_spec(
        skills_dir / "specs",
        "no_name",
        f"description: x\n{_VALID_SELECTION}\n",
    )
    try:
        SkillCatalog.load_catalog(skills_dir)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "no_name" in str(e)
        assert "name" in str(e)


PRODUCTION_SKILLS_DIR = (
    Path(__file__).resolve().parents[1] / "yoda" / "mind" / "agent" / "skills"
)


def test_production_catalog_static_dynamic_contrasts():
    catalog = SkillCatalog.load_catalog(PRODUCTION_SKILLS_DIR)
    by_name = {s.name: s for s in catalog}

    schedule = by_name["schedule_message"]
    search = by_name["search_web"]

    schedule_blob = "\n".join(
        [schedule.purpose]
        + schedule.when_to_use
        + schedule.do_not_use_when
        + schedule.selection_examples
    )
    search_blob = "\n".join(
        [search.purpose]
        + search.when_to_use
        + search.do_not_use_when
        + search.selection_examples
    )

    assert "витамины" in schedule_blob
    assert "актуальную погоду" in schedule_blob
    assert "search_web" in schedule_blob
    assert "лучше в девять" in schedule_blob
    assert "fresh-data" in schedule_blob or "monitoring" in schedule_blob

    assert "AccuWeather" in search_blob or "актуальн" in search_blob.lower()
    assert "проверить погоду" in search_blob
    assert "schedule_message" in search_blob
    assert "лучше в девять" in search_blob
    assert "reschedule" in search_blob or "time or recurrence" in search_blob

    # Order-neutral: reversing summaries must not change contract content.
    forward = [(s.name, s.purpose, tuple(s.when_to_use),
                tuple(s.do_not_use_when), tuple(s.selection_examples))
               for s in sorted(catalog, key=lambda x: x.name)]
    reversed_sorted = [
        (s.name, s.purpose, tuple(s.when_to_use),
         tuple(s.do_not_use_when), tuple(s.selection_examples))
        for s in sorted(list(reversed(catalog)), key=lambda x: x.name)
    ]
    assert forward == reversed_sorted


def test_search_web_workflow_declares_precedence_and_durable_write_boundary():
    search = SkillCatalog.load_skill(PRODUCTION_SKILLS_DIR, "search_web")
    instructions = search.instructions

    tiers = [
        "**Strict request constraints**",
        "**Soft request preferences**",
        "**Stored active-skill preferences**",
        "**Skill defaults**",
    ]
    positions = [instructions.index(tier) for tier in tiers]
    assert positions == sorted(positions)
    assert "One-off" in instructions
    assert "only when the user explicitly wants it from now on" in instructions
    assert "skill_preferences_to_add.search_web" in instructions
    assert "never `web_search`" in instructions


def _assert_iana_timezone_workflow(instructions: str) -> None:
    lower = instructions.lower()
    assert "iana" in lower
    assert "explicit" in lower
    assert "profile" in lower
    assert "unambiguous" in lower
    assert "update_profile" in instructions
    assert "ask_user" in instructions
    assert "current clock" in lower or "current local clock" in lower
    assert "+03:00" in instructions or "utc+03:00" in lower
    assert "delay_minutes" in instructions
    assert "no timezone" in lower or "no timezone clarification" in lower


def test_schedule_message_workflow_declares_iana_timezone_resolution():
    schedule = SkillCatalog.load_skill(PRODUCTION_SKILLS_DIR, "schedule_message")
    _assert_iana_timezone_workflow(schedule.instructions)
    assert "schedule_message" in schedule.instructions
    assert "Capability guard" in schedule.instructions
    assert 'mode="fail"' in schedule.instructions
    assert "failure_reason=\"unsupported\"" in schedule.instructions
    # Compact selection contract stays free of the ordered resolution policy.
    summary = next(
        s for s in SkillCatalog.load_catalog(PRODUCTION_SKILLS_DIR)
        if s.name == "schedule_message"
    )
    selection_blob = "\n".join(
        [summary.purpose]
        + summary.when_to_use
        + summary.do_not_use_when
        + summary.selection_examples
    )
    assert "IANA" not in selection_blob
    assert "unambiguous named location" not in selection_blob


def test_search_web_workflow_declares_iana_timezone_for_deferred_schedule():
    search = SkillCatalog.load_skill(PRODUCTION_SKILLS_DIR, "search_web")
    _assert_iana_timezone_workflow(search.instructions)
    assert "schedule_task" in search.instructions
    assert "skill_name=search_web" in search.instructions
    summary = next(
        s for s in SkillCatalog.load_catalog(PRODUCTION_SKILLS_DIR)
        if s.name == "search_web"
    )
    selection_blob = "\n".join(
        [summary.purpose]
        + summary.when_to_use
        + summary.do_not_use_when
        + summary.selection_examples
    )
    assert "IANA" not in selection_blob


def test_production_public_summaries_excludes_manage_user_data():
    catalog = SkillCatalog.load_catalog(PRODUCTION_SKILLS_DIR)
    names = {s.name for s in catalog}
    assert "manage_user_data" in names

    public = SkillCatalog.public_summaries(catalog)
    public_names = {s.name for s in public}
    assert "manage_user_data" not in public_names
    assert "schedule_message" in public_names
    assert "search_web" in public_names
