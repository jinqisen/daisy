from typing import List, Dict, Any, Optional
from datetime import datetime

from .loader import SkillLoader
from .models import (
    Skill,
    SkillMetadata,
    SkillStatus,
    ValidationResult
)
from .errors import (
    SkillNotFoundError,
    SkillDependencyError,
    SkillValidationError
)


class SkillDiscovery:
    def __init__(self, loader: SkillLoader):
        self.loader = loader
        self._skill_index: Dict[str, SkillMetadata] = {}
        self._category_index: Dict[str, List[str]] = {}
        self._tag_index: Dict[str, List[str]] = {}

    async def build_index(self) -> None:
        self._skill_index.clear()
        self._category_index.clear()
        self._tag_index.clear()

        skill_names = await self.loader.discover_skills()

        for skill_name in skill_names:
            try:
                metadata = self.loader.get_skill_metadata(skill_name)
                self._skill_index[skill_name] = metadata

                category = metadata.category or "uncategorized"
                if category not in self._category_index:
                    self._category_index[category] = []
                self._category_index[category].append(skill_name)

                for tag in metadata.tags:
                    if tag not in self._tag_index:
                        self._tag_index[tag] = []
                    self._tag_index[tag].append(skill_name)
            except Exception as e:
                print(f"Warning: Failed to index skill '{skill_name}': {e}")

    def get_all_skills(self) -> List[SkillMetadata]:
        return list(self._skill_index.values())

    def get_skill(self, skill_name: str) -> Optional[SkillMetadata]:
        return self._skill_index.get(skill_name)

    def find_skills_by_category(self, category: str) -> List[SkillMetadata]:
        skill_names = self._category_index.get(category, [])
        return [self._skill_index[name] for name in skill_names if name in self._skill_index]

    def find_skills_by_tag(self, tag: str) -> List[SkillMetadata]:
        skill_names = self._tag_index.get(tag, [])
        return [self._skill_index[name] for name in skill_names if name in self._skill_index]

    def search_skills(self, query: str) -> List[SkillMetadata]:
        query_lower = query.lower()
        results = []

        for skill_name, metadata in self._skill_index.items():
            if (query_lower in skill_name.lower() or
                query_lower in metadata.description.lower() or
                any(query_lower in tag.lower() for tag in metadata.tags)):
                results.append(metadata)

        return results

    def validate_dependencies(self, skill_name: str) -> ValidationResult:
        metadata = self.get_skill(skill_name)
        if not metadata:
            raise SkillNotFoundError(skill_name)

        errors = []
        warnings = []

        for dep in metadata.dependencies:
            if dep not in self._skill_index:
                errors.append(f"Dependency '{dep}' not found")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_all_skills(self) -> Dict[str, ValidationResult]:
        results = {}

        for skill_name in self._skill_index:
            try:
                validation_result = self.loader.validate_skill(skill_name)
                dep_validation = self.validate_dependencies(skill_name)

                combined_errors = validation_result.errors + dep_validation.errors
                combined_warnings = validation_result.warnings + dep_validation.warnings

                results[skill_name] = ValidationResult(
                    valid=len(combined_errors) == 0,
                    errors=combined_errors,
                    warnings=combined_warnings
                )
            except Exception as e:
                results[skill_name] = ValidationResult(
                    valid=False,
                    errors=[str(e)],
                    warnings=[]
                )

        return results

    def get_categories(self) -> List[str]:
        return sorted(self._category_index.keys())

    def get_tags(self) -> List[str]:
        return sorted(self._tag_index.keys())

    def get_skill_count(self) -> int:
        return len(self._skill_index)

    def is_skill_available(self, skill_name: str) -> bool:
        return skill_name in self._skill_index

    def get_skill_dependencies(self, skill_name: str) -> List[str]:
        metadata = self.get_skill(skill_name)
        return metadata.dependencies if metadata else []

    def get_dependent_skills(self, skill_name: str) -> List[str]:
        dependents = []

        for name, metadata in self._skill_index.items():
            if skill_name in metadata.dependencies:
                dependents.append(name)

        return dependents

    def refresh(self) -> None:
        self.loader.clear_cache()
        self.build_index()
