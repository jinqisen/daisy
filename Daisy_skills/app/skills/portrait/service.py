from __future__ import annotations

from typing import Any, Dict, List

from ...shared.utils import compact_texts


def generate_portrait(common_settings: Dict[str, Any], history_texts: List[str]) -> Dict[str, Any]:
    name = common_settings.get("name", "Daisy")
    relationship = common_settings.get("relationship", "friend")
    style = common_settings.get("style", [])
    summary = compact_texts(history_texts, 400)
    portrait_text = f"{name} is a {relationship}. Recent context: {summary}" if summary else f"{name} is a {relationship}."
    character_card = {
        "name": name,
        "relationship": relationship,
        "style": style,
        "summary": summary,
    }
    return {"portrait_text": portrait_text, "character_card": character_card}
