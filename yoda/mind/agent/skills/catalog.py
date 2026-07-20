import logging
from pathlib import Path

import yaml

from yoda.mind.agent.data.agent_data import SkillSpec, SkillSummary

logger = logging.getLogger(__name__)

_SELECTION_LIST_FIELDS = ("when_to_use", "do_not_use_when", "selection_examples")


class SkillCatalog:
    @staticmethod
    def load_catalog(skills_dir: Path) -> list[SkillSummary]:
        summaries: list[SkillSummary] = []
        specs_dir = skills_dir / "specs"
        if not specs_dir.exists():
            logger.warning(f"Skills specs directory not found: {specs_dir}")
            return summaries

        for md_file in sorted(specs_dir.glob("*.md")):
            frontmatter = SkillCatalog._parse_frontmatter(md_file)
            if frontmatter is None:
                raise ValueError(
                    f"Skill spec '{md_file.stem}' has no valid YAML frontmatter"
                )
            if "name" not in frontmatter or not str(frontmatter.get("name", "")).strip():
                raise ValueError(
                    f"Skill spec '{md_file.stem}' is missing required field 'name'"
                )
            SkillCatalog._validate_selection_metadata(md_file.stem, frontmatter)
            summaries.append(SkillSummary(
                name=frontmatter["name"],
                description=frontmatter.get("description", ""),
                public=frontmatter.get("public", True),
                purpose=str(frontmatter["purpose"]).strip(),
                when_to_use=list(frontmatter["when_to_use"]),
                do_not_use_when=list(frontmatter["do_not_use_when"]),
                selection_examples=list(frontmatter["selection_examples"]),
            ))

        return summaries

    @staticmethod
    def _validate_selection_metadata(stem: str, frontmatter: dict) -> None:
        skill_id = str(frontmatter.get("name") or stem).strip() or stem

        purpose = frontmatter.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            raise ValueError(
                f"Skill '{skill_id}' has invalid selection metadata field 'purpose'"
            )

        for field_name in _SELECTION_LIST_FIELDS:
            value = frontmatter.get(field_name)
            if not isinstance(value, list) or not value:
                raise ValueError(
                    f"Skill '{skill_id}' has invalid selection metadata "
                    f"field '{field_name}'"
                )
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError(
                        f"Skill '{skill_id}' has invalid selection metadata "
                        f"field '{field_name}'"
                    )

    @staticmethod
    def public_summaries(catalog: list[SkillSummary]) -> list[SkillSummary]:
        return [s for s in catalog if s.public]

    @staticmethod
    def load_skill(skills_dir: Path, skill_name: str) -> SkillSpec:
        specs_dir = skills_dir / "specs"
        for md_file in specs_dir.glob("*.md"):
            frontmatter = SkillCatalog._parse_frontmatter(md_file)
            if frontmatter and frontmatter.get("name") == skill_name:
                body = SkillCatalog._parse_body(md_file)
                return SkillSpec(
                    name=frontmatter["name"],
                    description=frontmatter.get("description", ""),
                    required_inputs=frontmatter.get("required_inputs", {}),
                    tools=frontmatter.get("tools", []),
                    instructions=body,
                    max_iterations=frontmatter.get("max_iterations", 10),
                )

        raise ValueError(f"Skill not found: {skill_name}")

    @staticmethod
    def validate_tools(
        catalog: list[SkillSummary],
        skills_dir: Path,
        available_tools: set[str],
    ) -> list[str]:
        """Return list of warnings for skills referencing unknown tools."""
        warnings: list[str] = []
        for summary in catalog:
            try:
                spec = SkillCatalog.load_skill(skills_dir, summary.name)
            except ValueError:
                continue
            unknown = set(spec.tools) - available_tools
            if unknown:
                warnings.append(
                    f"Skill '{spec.name}' references unknown tools: {unknown}")
        return warnings

    @staticmethod
    def _parse_frontmatter(md_file: Path) -> dict | None:
        text = md_file.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return None
        end = text.find("---", 3)
        if end == -1:
            return None
        return yaml.safe_load(text[3:end])

    @staticmethod
    def _parse_body(md_file: Path) -> str:
        text = md_file.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return text
        end = text.find("---", 3)
        if end == -1:
            return text
        return text[end + 3:].strip()
