import os
import yaml
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from .models import (
    Skill,
    SkillMetadata,
    SkillInstruction,
    SkillResource,
    SkillStatus,
    ResourceType,
    ValidationResult
)
from .errors import (
    SkillValidationError,
    SkillResourceError
)


class SkillLoader:
    def __init__(self, skills_dir: Optional[str] = None):
        self.skills_dir = Path(skills_dir) if skills_dir else None
        self._skills_cache: Dict[str, Skill] = {}

    async def discover_skills(self, skills_dir: Optional[str] = None) -> List[str]:
        if skills_dir:
            self.skills_dir = Path(skills_dir)
        
        if not self.skills_dir or not self.skills_dir.exists():
            return []
        
        skill_names = []
        for item in self.skills_dir.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                skill_names.append(item.name)
        return skill_names

    def load_skill(self, skill_name: str, force_reload: bool = False) -> Skill:
        if skill_name in self._skills_cache and not force_reload:
            return self._skills_cache[skill_name]

        if not self.skills_dir:
            raise SkillResourceError(skill_name, "", "Skills directory not configured")

        skill_path = self.skills_dir / skill_name
        if not skill_path.exists():
            raise SkillResourceError(skill_name, str(skill_path), "Skill directory not found")

        skill_md_path = skill_path / "SKILL.md"
        if not skill_md_path.exists():
            raise SkillResourceError(skill_name, str(skill_md_path), "SKILL.md not found")

        metadata, instruction = self._parse_skill_md(skill_md_path)
        resources = self._load_resources(skill_path)

        skill = Skill(
            metadata=metadata,
            instruction=instruction,
            resources=resources,
            path=str(skill_path)
        )

        self._skills_cache[skill_name] = skill
        return skill

    def _parse_skill_md(self, skill_md_path: Path) -> tuple[SkillMetadata, SkillInstruction]:
        with open(skill_md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if not content.startswith('---'):
            raise SkillValidationError("", ["SKILL.md must start with YAML frontmatter"])

        parts = content.split('---', 2)
        if len(parts) < 3:
            raise SkillValidationError("", ["SKILL.md must have YAML frontmatter and content"])

        frontmatter = parts[1]
        markdown_content = parts[2].strip()

        try:
            metadata_dict = yaml.safe_load(frontmatter)
        except yaml.YAMLError as e:
            raise SkillValidationError("", [f"Invalid YAML frontmatter: {e}"])

        metadata = self._parse_metadata(metadata_dict)
        instruction = self._parse_instruction(markdown_content)

        return metadata, instruction

    def _parse_metadata(self, metadata_dict: Dict[str, Any]) -> SkillMetadata:
        required_fields = ['name', 'description', 'version', 'license']
        missing_fields = [f for f in required_fields if f not in metadata_dict]
        if missing_fields:
            raise SkillValidationError("", [f"Missing required metadata fields: {', '.join(missing_fields)}"])

        return SkillMetadata(
            name=metadata_dict['name'],
            description=metadata_dict['description'],
            version=metadata_dict['version'],
            license=metadata_dict['license'],
            author=metadata_dict.get('metadata', {}).get('author', ''),
            category=metadata_dict.get('metadata', {}).get('category', ''),
            tags=metadata_dict.get('metadata', {}).get('tags', []),
            dependencies=metadata_dict.get('dependencies', []),
            allowed_tools=metadata_dict.get('allowed-tools', []),
            status=SkillStatus.ACTIVE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    def _parse_instruction(self, markdown_content: str) -> SkillInstruction:
        sections = {}
        current_section = "main"
        current_content = []

        for line in markdown_content.split('\n'):
            if line.startswith('# '):
                if current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = line[2:].strip().lower()
                current_content = []
            else:
                current_content.append(line)

        if current_content:
            sections[current_section] = '\n'.join(current_content).strip()

        examples = self._extract_examples(markdown_content)

        return SkillInstruction(
            content=markdown_content,
            sections=sections,
            examples=examples
        )

    def _extract_examples(self, markdown_content: str) -> List[Dict[str, Any]]:
        examples = []
        in_example = False
        current_example = {}

        for line in markdown_content.split('\n'):
            if line.strip().startswith('```'):
                if in_example:
                    current_example['code'] = current_example.get('code', '') + '\n' + line
                    examples.append(current_example)
                    current_example = {}
                    in_example = False
                else:
                    in_example = True
                    current_example['language'] = line[3:].strip()
                    current_example['code'] = ''
            elif in_example:
                current_example['code'] = current_example.get('code', '') + '\n' + line

        return examples

    def _load_resources(self, skill_path: Path) -> List[SkillResource]:
        resources = []

        scripts_dir = skill_path / "scripts"
        if scripts_dir.exists():
            for script_file in scripts_dir.glob("*.py"):
                resources.append(SkillResource(
                    type=ResourceType.SCRIPT,
                    path=str(script_file),
                    name=script_file.stem,
                    metadata={"language": "python"}
                ))

        references_dir = skill_path / "references"
        if references_dir.exists():
            for ref_file in references_dir.glob("*.md"):
                resources.append(SkillResource(
                    type=ResourceType.REFERENCE,
                    path=str(ref_file),
                    name=ref_file.stem,
                    metadata={"format": "markdown"}
                ))

        assets_dir = skill_path / "assets"
        if assets_dir.exists():
            for asset_file in assets_dir.glob("*"):
                if asset_file.is_file():
                    resources.append(SkillResource(
                        type=ResourceType.ASSET,
                        path=str(asset_file),
                        name=asset_file.name,
                        metadata={"extension": asset_file.suffix}
                    ))

        config_file = skill_path / "assets" / "config.json"
        if config_file.exists():
            resources.append(SkillResource(
                type=ResourceType.CONFIG,
                path=str(config_file),
                name="config",
                metadata={"format": "json"}
            ))

        return resources

    def validate_skill(self, skill_name: str) -> ValidationResult:
        try:
            skill = self.load_skill(skill_name)
            errors = []
            warnings = []

            if not skill.metadata.name:
                errors.append("Skill name is empty")

            if not skill.metadata.description:
                warnings.append("Skill description is empty")

            if not skill.resources:
                warnings.append("Skill has no resources")

            return ValidationResult(
                valid=len(errors) == 0,
                errors=errors,
                warnings=warnings
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                errors=[str(e)],
                warnings=[]
            )

    def get_skill_metadata(self, skill_name: str) -> SkillMetadata:
        skill = self.load_skill(skill_name)
        return skill.metadata

    def get_skill_instruction(self, skill_name: str) -> SkillInstruction:
        skill = self.load_skill(skill_name)
        return skill.instruction

    def get_skill_resources(self, skill_name: str) -> List[SkillResource]:
        skill = self.load_skill(skill_name)
        return skill.resources

    def reload_skill(self, skill_name: str) -> Skill:
        return self.load_skill(skill_name, force_reload=True)

    def clear_cache(self):
        self._skills_cache.clear()
