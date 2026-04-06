from pathlib import Path

from yoda.mind.agent.skills.catalog import SkillCatalog

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "skills"


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
