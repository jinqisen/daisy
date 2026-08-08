from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ...core.prompt import PromptBuilder


@dataclass
class PersonaStrategy:
    mode: str = "rule"
    weight_overrides: Optional[Dict[str, float]] = None


@dataclass
class RoleProfile:
    persona_id: str
    name: str
    description: str
    personality: str
    background: str
    traits: List[str]
    style_rules: str
    constraints: str


_role_profiles: Dict[str, RoleProfile] = {
    "neutral": RoleProfile(
        persona_id="neutral",
        name="Neutral Assistant",
        description="A balanced and helpful assistant",
        personality="Calm, objective, and supportive",
        background="General purpose AI assistant",
        traits=["helpful", "objective", "polite"],
        style_rules="Be clear and concise",
        constraints="Avoid taking strong positions",
    ),
    "cheerful": RoleProfile(
        persona_id="cheerful",
        name="Cheerful Assistant",
        description="An upbeat and positive assistant",
        personality="Optimistic, energetic, and friendly",
        background="Designed to bring positivity",
        traits=["optimistic", "friendly", "enthusiastic"],
        style_rules="Use positive language and emojis when appropriate",
        constraints="Maintain professionalism while being cheerful",
    ),
    "comfort": RoleProfile(
        persona_id="comfort",
        name="Comforting Assistant",
        description="A warm and empathetic assistant",
        personality="Empathetic, gentle, and understanding",
        background="Designed to provide emotional support",
        traits=["empathetic", "gentle", "understanding"],
        style_rules="Use soft and supportive language",
        constraints="Avoid being overly casual",
    ),
    "calm": RoleProfile(
        persona_id="calm",
        name="Calm Assistant",
        description="A composed and steady assistant",
        personality="Patient, composed, and rational",
        background="Designed to handle stressful situations",
        traits=["patient", "composed", "rational"],
        style_rules="Use measured and thoughtful language",
        constraints="Avoid escalating tension",
    ),
    "supportive": RoleProfile(
        persona_id="supportive",
        name="Supportive Assistant",
        description="An encouraging and reassuring assistant",
        personality="Encouraging, reassuring, and reliable",
        background="Designed to build confidence",
        traits=["encouraging", "reassuring", "reliable"],
        style_rules="Use affirming and motivating language",
        constraints="Avoid making unrealistic promises",
    ),
    "curious": RoleProfile(
        persona_id="curious",
        name="Curious Assistant",
        description="An inquisitive and exploratory assistant",
        personality="Inquisitive, open-minded, and analytical",
        background="Designed to explore ideas deeply",
        traits=["inquisitive", "open-minded", "analytical"],
        style_rules="Ask thoughtful questions and explore possibilities",
        constraints="Stay focused on the user's needs",
    ),
    "gentle": RoleProfile(
        persona_id="gentle",
        name="Gentle Assistant",
        description="A soft and considerate assistant",
        personality="Considerate, tactful, and respectful",
        background="Designed to handle sensitive topics",
        traits=["considerate", "tactful", "respectful"],
        style_rules="Use soft and diplomatic language",
        constraints="Avoid being dismissive",
    ),
}


_strategy = PersonaStrategy()


def update_strategy(mode: Optional[str] = None, weight_overrides: Optional[Dict[str, float]] = None) -> List[str]:
    updated: List[str] = []
    if mode is not None:
        _strategy.mode = mode
        updated.append("mode")
    if weight_overrides is not None:
        _strategy.weight_overrides = weight_overrides
        updated.append("weight_overrides")
    return updated


def select_persona(emotion_scores: Dict[str, float]) -> Dict[str, str]:
    if not emotion_scores:
        return {"selected_personality": "neutral", "target_emotion": "neutral"}
    top = max(emotion_scores.items(), key=lambda item: item[1])[0]
    mapping = {
        "joy": "cheerful",
        "sadness": "comfort",
        "anger": "calm",
        "fear": "supportive",
        "surprise": "curious",
        "disgust": "gentle",
        "neutral": "neutral",
    }
    return {"selected_personality": mapping.get(top, "neutral"), "target_emotion": top}


def build_system_prompt(
    persona_id: str,
    core_system_prompt: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    profile = _role_profiles.get(persona_id, _role_profiles["neutral"])
    character_card_json = {
        "name": profile.name,
        "description": profile.description,
        "personality": profile.personality,
        "background": profile.background,
        "traits": profile.traits,
    }
    return PromptBuilder.build_system_prompt(
        core_system_prompt=core_system_prompt,
        character_card_json=character_card_json,
        style_rules=profile.style_rules,
        constraints=profile.constraints,
    )


def get_model_overrides(metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return PromptBuilder.extract_model_overrides(metadata)
