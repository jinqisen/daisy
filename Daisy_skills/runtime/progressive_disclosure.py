from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import json
from .models import SkillMetadata, SkillContext


class DisclosureLevel(Enum):
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ParameterVisibility(Enum):
    ALWAYS = "always"
    CONTEXT_AWARE = "context_aware"
    ON_DEMAND = "on_demand"
    HIDDEN = "hidden"


@dataclass
class ParameterDisclosure:
    name: str
    visibility: ParameterVisibility
    level: DisclosureLevel
    description: str
    required: bool = False
    default_value: Any = None
    depends_on: Optional[List[str]] = None
    validation_rules: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityDisclosure:
    name: str
    level: DisclosureLevel
    description: str
    required_permissions: List[str] = field(default_factory=list)
    estimated_complexity: int = 1
    estimated_duration_ms: int = 1000
    dependencies: List[str] = field(default_factory=list)


@dataclass
class SkillDisclosureProfile:
    skill_name: str
    basic_capabilities: List[CapabilityDisclosure]
    intermediate_capabilities: List[CapabilityDisclosure]
    advanced_capabilities: List[CapabilityDisclosure]
    expert_capabilities: List[CapabilityDisclosure]
    parameters: List[ParameterDisclosure]
    default_level: DisclosureLevel = DisclosureLevel.BASIC


@dataclass
class DisclosureContext:
    user_id: str
    session_id: str
    skill_name: str
    current_level: DisclosureLevel
    interaction_count: int = 0
    success_rate: float = 1.0
    time_spent_ms: int = 0
    previous_errors: List[str] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DisclosureResult:
    visible_capabilities: List[Dict[str, Any]]
    visible_parameters: List[Dict[str, Any]]
    suggested_level: DisclosureLevel
    next_level_requirements: Optional[Dict[str, Any]] = None
    hints: List[str] = field(default_factory=list)


class ProgressiveDisclosureEngine:
    def __init__(self):
        self._profiles: Dict[str, SkillDisclosureProfile] = {}
        self._user_contexts: Dict[str, DisclosureContext] = {}
        self._level_thresholds = {
            DisclosureLevel.BASIC: {"min_interactions": 0, "min_success_rate": 0.0},
            DisclosureLevel.INTERMEDIATE: {"min_interactions": 3, "min_success_rate": 0.7},
            DisclosureLevel.ADVANCED: {"min_interactions": 10, "min_success_rate": 0.8},
            DisclosureLevel.EXPERT: {"min_interactions": 20, "min_success_rate": 0.9},
        }

    def register_profile(self, profile: SkillDisclosureProfile) -> None:
        self._profiles[profile.skill_name] = profile

    def get_profile(self, skill_name: str) -> Optional[SkillDisclosureProfile]:
        return self._profiles.get(skill_name)

    def create_context(
        self,
        user_id: str,
        session_id: str,
        skill_name: str,
        initial_level: DisclosureLevel = DisclosureLevel.BASIC
    ) -> DisclosureContext:
        context_key = f"{user_id}:{session_id}:{skill_name}"
        context = DisclosureContext(
            user_id=user_id,
            session_id=session_id,
            skill_name=skill_name,
            current_level=initial_level
        )
        self._user_contexts[context_key] = context
        return context

    def get_context(self, user_id: str, session_id: str, skill_name: str) -> Optional[DisclosureContext]:
        context_key = f"{user_id}:{session_id}:{skill_name}"
        return self._user_contexts.get(context_key)

    def update_context(
        self,
        user_id: str,
        session_id: str,
        skill_name: str,
        success: bool,
        duration_ms: int,
        error: Optional[str] = None
    ) -> None:
        context = self.get_context(user_id, session_id, skill_name)
        if not context:
            return

        context.interaction_count += 1
        context.time_spent_ms += duration_ms

        if success:
            context.success_rate = (
                context.success_rate * (context.interaction_count - 1) + 1.0
            ) / context.interaction_count
        else:
            context.success_rate = (
                context.success_rate * (context.interaction_count - 1) + 0.0
            ) / context.interaction_count
            if error:
                context.previous_errors.append(error)
                if len(context.previous_errors) > 10:
                    context.previous_errors.pop(0)

    def calculate_suggested_level(self, context: DisclosureContext) -> DisclosureLevel:
        thresholds = self._level_thresholds
        suggested = DisclosureLevel.BASIC

        for level in [DisclosureLevel.INTERMEDIATE, DisclosureLevel.ADVANCED, DisclosureLevel.EXPERT]:
            threshold = thresholds[level]
            if (context.interaction_count >= threshold["min_interactions"] and
                context.success_rate >= threshold["min_success_rate"]):
                suggested = level

        return suggested

    def get_disclosure(
        self,
        skill_name: str,
        context: DisclosureContext,
        force_level: Optional[DisclosureLevel] = None
    ) -> DisclosureResult:
        profile = self.get_profile(skill_name)
        if not profile:
            return DisclosureResult(
                visible_capabilities=[],
                visible_parameters=[],
                suggested_level=DisclosureLevel.BASIC,
                hints=["Skill profile not found"]
            )

        level = force_level or context.current_level
        suggested_level = self.calculate_suggested_level(context)

        visible_capabilities = self._get_visible_capabilities(profile, level)
        visible_parameters = self._get_visible_parameters(profile, level, context)
        hints = self._generate_hints(profile, level, suggested_level, context)

        next_level_requirements = None
        if suggested_level != level:
            next_level_requirements = self._get_next_level_requirements(suggested_level)

        return DisclosureResult(
            visible_capabilities=visible_capabilities,
            visible_parameters=visible_parameters,
            suggested_level=suggested_level,
            next_level_requirements=next_level_requirements,
            hints=hints
        )

    def _get_visible_capabilities(
        self,
        profile: SkillDisclosureProfile,
        level: DisclosureLevel
    ) -> List[Dict[str, Any]]:
        capabilities = []

        level_order = [
            DisclosureLevel.BASIC,
            DisclosureLevel.INTERMEDIATE,
            DisclosureLevel.ADVANCED,
            DisclosureLevel.EXPERT
        ]

        current_level_index = level_order.index(level)

        for cap_level in level_order[:current_level_index + 1]:
            if cap_level == DisclosureLevel.BASIC:
                capabilities.extend(profile.basic_capabilities)
            elif cap_level == DisclosureLevel.INTERMEDIATE:
                capabilities.extend(profile.intermediate_capabilities)
            elif cap_level == DisclosureLevel.ADVANCED:
                capabilities.extend(profile.advanced_capabilities)
            elif cap_level == DisclosureLevel.EXPERT:
                capabilities.extend(profile.expert_capabilities)

        return [
            {
                "name": cap.name,
                "level": cap.level.value,
                "description": cap.description,
                "required_permissions": cap.required_permissions,
                "estimated_complexity": cap.estimated_complexity,
                "estimated_duration_ms": cap.estimated_duration_ms,
                "dependencies": cap.dependencies
            }
            for cap in capabilities
        ]

    def _get_visible_parameters(
        self,
        profile: SkillDisclosureProfile,
        level: DisclosureLevel,
        context: DisclosureContext
    ) -> List[Dict[str, Any]]:
        visible_params = []

        for param in profile.parameters:
            if param.visibility == ParameterVisibility.HIDDEN:
                continue

            if param.visibility == ParameterVisibility.ALWAYS:
                visible_params.append(param)
                continue

            if param.visibility == ParameterVisibility.CONTEXT_AWARE:
                if self._should_show_context_aware(param, context):
                    visible_params.append(param)
                continue

            if param.visibility == ParameterVisibility.ON_DEMAND:
                if level.value in ["advanced", "expert"]:
                    visible_params.append(param)
                continue

        return [
            {
                "name": p.name,
                "visibility": p.visibility.value,
                "level": p.level.value,
                "description": p.description,
                "required": p.required,
                "default_value": p.default_value,
                "depends_on": p.depends_on,
                "validation_rules": p.validation_rules
            }
            for p in visible_params
        ]

    def _should_show_context_aware(
        self,
        param: ParameterDisclosure,
        context: DisclosureContext
    ) -> bool:
        if param.depends_on:
            for dep in param.depends_on:
                if dep not in context.user_preferences:
                    return False

        if param.level == DisclosureLevel.BASIC:
            return True
        elif param.level == DisclosureLevel.INTERMEDIATE:
            return context.interaction_count >= 3
        elif param.level == DisclosureLevel.ADVANCED:
            return context.interaction_count >= 10
        elif param.level == DisclosureLevel.EXPERT:
            return context.interaction_count >= 20

        return False

    def _generate_hints(
        self,
        profile: SkillDisclosureProfile,
        current_level: DisclosureLevel,
        suggested_level: DisclosureLevel,
        context: DisclosureContext
    ) -> List[str]:
        hints = []

        if suggested_level != current_level:
            hints.append(
                f"You can unlock more capabilities by using this skill more. "
                f"Current: {current_level.value}, Suggested: {suggested_level.value}"
            )

        if context.previous_errors:
            hints.append(
                f"Recent errors: {', '.join(context.previous_errors[-3:])}. "
                "Consider reviewing the parameter requirements."
            )

        if context.interaction_count == 0:
            hints.append("Start with basic capabilities to get familiar with this skill.")

        return hints

    def _get_next_level_requirements(self, level: DisclosureLevel) -> Dict[str, Any]:
        threshold = self._level_thresholds.get(level, {})
        return {
            "level": level.value,
            "min_interactions": threshold.get("min_interactions", 0),
            "min_success_rate": threshold.get("min_success_rate", 0.0)
        }

    def upgrade_level(
        self,
        user_id: str,
        session_id: str,
        skill_name: str,
        target_level: DisclosureLevel
    ) -> bool:
        context = self.get_context(user_id, session_id, skill_name)
        if not context:
            return False

        suggested = self.calculate_suggested_level(context)
        level_order = [
            DisclosureLevel.BASIC,
            DisclosureLevel.INTERMEDIATE,
            DisclosureLevel.ADVANCED,
            DisclosureLevel.EXPERT
        ]

        if level_order.index(target_level) <= level_order.index(suggested):
            context.current_level = target_level
            return True

        return False

    def reset_context(self, user_id: str, session_id: str, skill_name: str) -> None:
        context_key = f"{user_id}:{session_id}:{skill_name}"
        if context_key in self._user_contexts:
            del self._user_contexts[context_key]

    def get_user_progress(
        self,
        user_id: str,
        session_id: str,
        skill_name: str
    ) -> Optional[Dict[str, Any]]:
        context = self.get_context(user_id, session_id, skill_name)
        if not context:
            return None

        suggested = self.calculate_suggested_level(context)

        return {
            "user_id": context.user_id,
            "session_id": context.session_id,
            "skill_name": context.skill_name,
            "current_level": context.current_level.value,
            "suggested_level": suggested.value,
            "interaction_count": context.interaction_count,
            "success_rate": context.success_rate,
            "time_spent_ms": context.time_spent_ms,
            "recent_errors": context.previous_errors[-5:] if context.previous_errors else []
        }

    def export_profile(self, skill_name: str) -> Optional[Dict[str, Any]]:
        profile = self.get_profile(skill_name)
        if not profile:
            return None

        return {
            "skill_name": profile.skill_name,
            "default_level": profile.default_level.value,
            "basic_capabilities": [
                {
                    "name": cap.name,
                    "level": cap.level.value,
                    "description": cap.description,
                    "required_permissions": cap.required_permissions,
                    "estimated_complexity": cap.estimated_complexity,
                    "estimated_duration_ms": cap.estimated_duration_ms,
                    "dependencies": cap.dependencies
                }
                for cap in profile.basic_capabilities
            ],
            "intermediate_capabilities": [
                {
                    "name": cap.name,
                    "level": cap.level.value,
                    "description": cap.description,
                    "required_permissions": cap.required_permissions,
                    "estimated_complexity": cap.estimated_complexity,
                    "estimated_duration_ms": cap.estimated_duration_ms,
                    "dependencies": cap.dependencies
                }
                for cap in profile.intermediate_capabilities
            ],
            "advanced_capabilities": [
                {
                    "name": cap.name,
                    "level": cap.level.value,
                    "description": cap.description,
                    "required_permissions": cap.required_permissions,
                    "estimated_complexity": cap.estimated_complexity,
                    "estimated_duration_ms": cap.estimated_duration_ms,
                    "dependencies": cap.dependencies
                }
                for cap in profile.advanced_capabilities
            ],
            "expert_capabilities": [
                {
                    "name": cap.name,
                    "level": cap.level.value,
                    "description": cap.description,
                    "required_permissions": cap.required_permissions,
                    "estimated_complexity": cap.estimated_complexity,
                    "estimated_duration_ms": cap.estimated_duration_ms,
                    "dependencies": cap.dependencies
                }
                for cap in profile.expert_capabilities
            ],
            "parameters": [
                {
                    "name": p.name,
                    "visibility": p.visibility.value,
                    "level": p.level.value,
                    "description": p.description,
                    "required": p.required,
                    "default_value": p.default_value,
                    "depends_on": p.depends_on,
                    "validation_rules": p.validation_rules
                }
                for p in profile.parameters
            ]
        }

    def import_profile(self, profile_data: Dict[str, Any]) -> bool:
        try:
            skill_name = profile_data["skill_name"]
            default_level = DisclosureLevel(profile_data.get("default_level", "basic"))

            def parse_capabilities(cap_list: List[Dict]) -> List[CapabilityDisclosure]:
                return [
                    CapabilityDisclosure(
                        name=cap["name"],
                        level=DisclosureLevel(cap["level"]),
                        description=cap["description"],
                        required_permissions=cap.get("required_permissions", []),
                        estimated_complexity=cap.get("estimated_complexity", 1),
                        estimated_duration_ms=cap.get("estimated_duration_ms", 1000),
                        dependencies=cap.get("dependencies", [])
                    )
                    for cap in cap_list
                ]

            def parse_parameters(param_list: List[Dict]) -> List[ParameterDisclosure]:
                return [
                    ParameterDisclosure(
                        name=p["name"],
                        visibility=ParameterVisibility(p["visibility"]),
                        level=DisclosureLevel(p["level"]),
                        description=p["description"],
                        required=p.get("required", False),
                        default_value=p.get("default_value"),
                        depends_on=p.get("depends_on"),
                        validation_rules=p.get("validation_rules", {})
                    )
                    for p in param_list
                ]

            profile = SkillDisclosureProfile(
                skill_name=skill_name,
                basic_capabilities=parse_capabilities(profile_data.get("basic_capabilities", [])),
                intermediate_capabilities=parse_capabilities(profile_data.get("intermediate_capabilities", [])),
                advanced_capabilities=parse_capabilities(profile_data.get("advanced_capabilities", [])),
                expert_capabilities=parse_capabilities(profile_data.get("expert_capabilities", [])),
                parameters=parse_parameters(profile_data.get("parameters", [])),
                default_level=default_level
            )

            self.register_profile(profile)
            return True
        except Exception:
            return False
