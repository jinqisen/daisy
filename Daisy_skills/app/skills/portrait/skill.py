from typing import Any, Dict, List, Optional
from datetime import datetime


_portrait_store: Dict[str, Dict[str, Any]] = {}


def _compact_texts(texts: List[str], max_chars: int = 400) -> str:
    result = []
    current_length = 0
    for text in texts:
        if current_length + len(text) > max_chars:
            remaining = max_chars - current_length
            if remaining > 0:
                result.append(text[:remaining])
            break
        result.append(text)
        current_length += len(text)
    return " ".join(result)


async def generate(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    user_id = input_data.get("user_id", "")
    common_settings = input_data.get("common_settings", {})
    history = input_data.get("history", [])
    persona_id = input_data.get("persona_id", "")
    
    name = common_settings.get("name", "Daisy")
    relationship = common_settings.get("relationship", "friend")
    style = common_settings.get("style", [])
    personality = common_settings.get("personality", "")
    background = common_settings.get("background", "")
    
    history_texts = [msg.get("content", "") if isinstance(msg, dict) else str(msg) for msg in history]
    summary = _compact_texts(history_texts, 400)
    
    portrait_parts = [f"{name} is a {relationship}."]
    
    if personality:
        portrait_parts.append(f"Personality: {personality}")
    
    if background:
        portrait_parts.append(f"Background: {background}")
    
    if style:
        portrait_parts.append(f"Style: {', '.join(style)}")
    
    if summary:
        portrait_parts.append(f"Recent context: {summary}")
    
    portrait_text = " ".join(portrait_parts)
    
    character_card = {
        "name": name,
        "relationship": relationship,
        "style": style,
        "personality": personality,
        "background": background,
        "summary": summary,
        "persona_id": persona_id
    }
    
    _portrait_store[user_id] = {
        "portrait_text": portrait_text,
        "character_card": character_card,
        "updated_at": datetime.utcnow().isoformat()
    }
    
    return {
        "portrait_text": portrait_text,
        "character_card": character_card,
        "metadata": {
            "user_id": user_id,
            "persona_id": persona_id,
            "timestamp": datetime.utcnow().isoformat()
        }
    }


async def update(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    user_id = input_data.get("user_id", "")
    settings = input_data.get("settings", {})
    
    if user_id not in _portrait_store:
        return {
            "status": "error",
            "message": "Portrait not found for user",
            "updated_fields": []
        }
    
    updated_fields = []
    portrait = _portrait_store[user_id]
    
    for key, value in settings.items():
        if key in portrait["character_card"]:
            portrait["character_card"][key] = value
            updated_fields.append(key)
    
    portrait["updated_at"] = datetime.utcnow().isoformat()
    
    name = portrait["character_card"].get("name", "Daisy")
    relationship = portrait["character_card"].get("relationship", "friend")
    style = portrait["character_card"].get("style", [])
    personality = portrait["character_card"].get("personality", "")
    background = portrait["character_card"].get("background", "")
    summary = portrait["character_card"].get("summary", "")
    
    portrait_parts = [f"{name} is a {relationship}."]
    
    if personality:
        portrait_parts.append(f"Personality: {personality}")
    
    if background:
        portrait_parts.append(f"Background: {background}")
    
    if style:
        portrait_parts.append(f"Style: {', '.join(style)}")
    
    if summary:
        portrait_parts.append(f"Recent context: {summary}")
    
    portrait["portrait_text"] = " ".join(portrait_parts)
    
    return {
        "status": "ok",
        "message": "Portrait updated successfully",
        "updated_fields": updated_fields,
        "portrait": portrait
    }


async def get(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    user_id = input_data.get("user_id", "")
    
    if user_id not in _portrait_store:
        return {
            "status": "error",
            "message": "Portrait not found for user",
            "portrait": None
        }
    
    portrait = _portrait_store[user_id]
    
    return {
        "status": "ok",
        "portrait": portrait
    }


__all__ = ["generate", "update", "get"]
