from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from datetime import datetime


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


def _map_emotion_to_persona(emotion: str) -> str:
    mapping = {
        "joy": "cheerful",
        "sadness": "comfort",
        "anger": "calm",
        "fear": "supportive",
        "surprise": "curious",
        "disgust": "gentle",
        "neutral": "neutral",
    }
    return mapping.get(emotion, "neutral")


def _calculate_weights(emotion_scores: Dict[str, float]) -> Dict[str, float]:
    weights = {}
    for emotion, score in emotion_scores.items():
        persona = _map_emotion_to_persona(emotion)
        weights[persona] = weights.get(persona, 0.0) + score
    
    if _strategy.weight_overrides:
        for persona, override_weight in _strategy.weight_overrides.items():
            weights[persona] = override_weight
    
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    
    return weights


async def select(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    user_id = input_data.get("user_id", "")
    emotion_scores = input_data.get("emotion_scores", {})
    ekman_scores = input_data.get("ekman_scores", {})
    mode = input_data.get("mode", "rule")
    context_summary = input_data.get("context_summary", "")
    
    if not emotion_scores:
        return {
            "selected_personality": "neutral",
            "weights": {"neutral": 1.0},
            "target_emotion": "neutral",
            "metadata": {
                "user_id": user_id,
                "mode": mode,
                "reason": "No emotion scores provided"
            }
        }
    
    top_emotion = max(emotion_scores.items(), key=lambda item: item[1])[0]
    selected_personality = _map_emotion_to_persona(top_emotion)
    weights = _calculate_weights(emotion_scores)
    
    return {
        "selected_personality": selected_personality,
        "weights": weights,
        "target_emotion": top_emotion,
        "metadata": {
            "user_id": user_id,
            "mode": mode,
            "context_summary": context_summary,
            "ekman_scores": ekman_scores,
            "timestamp": datetime.utcnow().isoformat()
        }
    }


async def update_strategy(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    updated_fields = []
    
    mode = input_data.get("mode")
    if mode is not None:
        _strategy.mode = mode
        updated_fields.append("mode")
    
    weight_overrides = input_data.get("weight_overrides")
    if weight_overrides is not None:
        _strategy.weight_overrides = weight_overrides
        updated_fields.append("weight_overrides")
    
    return {
        "status": "ok",
        "message": "Strategy updated successfully",
        "updated_fields": updated_fields,
        "current_strategy": {
            "mode": _strategy.mode,
            "weight_overrides": _strategy.weight_overrides
        }
    }


async def build_system_prompt(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    persona_id = input_data.get("persona_id", "neutral")
    core_system_prompt = input_data.get("core_system_prompt", "")
    metadata = input_data.get("metadata", {})
    
    profile = _role_profiles.get(persona_id, _role_profiles["neutral"])
    
    character_card = {
        "name": profile.name,
        "description": profile.description,
        "personality": profile.personality,
        "background": profile.background,
        "traits": profile.traits,
    }
    
    system_prompt = f"""{core_system_prompt}

You are {profile.name}.
{profile.description}

Personality: {profile.personality}
Background: {profile.background}

Traits: {', '.join(profile.traits)}

Style Rules:
{profile.style_rules}

Constraints:
{profile.constraints}
"""
    
    return {
        "system_prompt": system_prompt,
        "persona_info": {
            "persona_id": profile.persona_id,
            "name": profile.name,
            "description": profile.description,
            "personality": profile.personality,
            "background": profile.background,
            "traits": profile.traits,
            "style_rules": profile.style_rules,
            "constraints": profile.constraints
        },
        "character_card": character_card,
        "metadata": {
            "timestamp": datetime.utcnow().isoformat()
        }
    }


async def get_profile(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    persona_id = input_data.get("persona_id", "neutral")
    profile = _role_profiles.get(persona_id, _role_profiles["neutral"])
    
    return {
        "profile": {
            "persona_id": profile.persona_id,
            "name": profile.name,
            "description": profile.description,
            "personality": profile.personality,
            "background": profile.background,
            "traits": profile.traits,
            "style_rules": profile.style_rules,
            "constraints": profile.constraints
        },
        "available_personas": list(_role_profiles.keys())
    }


__all__ = ["select", "update_strategy", "build_system_prompt", "get_profile"]
