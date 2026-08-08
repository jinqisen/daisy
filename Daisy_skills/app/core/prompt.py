from __future__ import annotations

from typing import Any, Dict, Optional


DEFAULT_SAFETY_RULES = """
1. Do not generate harmful, illegal, or explicit content
2. Respect user privacy and do not ask for sensitive information
3. Be helpful and honest
4. Do not impersonate real people without permission
"""


class PromptBuilder:
    SEPARATOR = "\n\n"

    @staticmethod
    def build_system_prompt(
        core_system_prompt: str,
        character_card_text: Optional[str] = None,
        character_card_json: Optional[Dict[str, Any]] = None,
        style_rules: Optional[str] = None,
        constraints: Optional[str] = None,
        safety_rules: Optional[str] = None,
    ) -> str:
        sections = []

        sections.append(f"[CORE]\n{core_system_prompt}")

        if character_card_json:
            summary = PromptBuilder._summarize_character_card(character_card_json)
            sections.append(f"[CHARACTER_CARD]\n{summary}")
        elif character_card_text:
            sections.append(f"[CHARACTER_CARD]\n{character_card_text}")

        if style_rules:
            sections.append(f"[STYLE]\n{style_rules}")

        if constraints:
            sections.append(f"[CONSTRAINTS]\n{constraints}")

        safety = safety_rules or DEFAULT_SAFETY_RULES
        sections.append(f"[SAFETY]\n{safety}")

        return PromptBuilder.SEPARATOR.join(sections)

    @staticmethod
    def _summarize_character_card(card_json: Dict[str, Any]) -> str:
        parts = []
        if "name" in card_json:
            parts.append(f"Name: {card_json['name']}")
        if "description" in card_json:
            parts.append(f"Description: {card_json['description']}")
        if "personality" in card_json:
            parts.append(f"Personality: {card_json['personality']}")
        if "background" in card_json:
            parts.append(f"Background: {card_json['background']}")
        if "traits" in card_json:
            traits = card_json["traits"]
            if isinstance(traits, list):
                parts.append(f"Traits: {', '.join(traits)}")
            else:
                parts.append(f"Traits: {traits}")
        return "\n".join(parts)

    @staticmethod
    def extract_model_overrides(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        ALLOWED_KEYS = {
            "provider",
            "base_url",
            "model_name",
            "temperature",
            "max_tokens",
            "timeout_sec",
        }

        overrides = {}
        if not metadata:
            return overrides

        model_meta = metadata.get("model", {})
        if not isinstance(model_meta, dict):
            return overrides

        for key, value in model_meta.items():
            if key in ALLOWED_KEYS:
                overrides[key] = value

        return overrides

    @staticmethod
    def apply_model_overrides(base_config: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
        config = base_config.copy()
        config.update(overrides)
        return config
