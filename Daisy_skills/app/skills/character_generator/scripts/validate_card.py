from typing import Dict, Any
from runtime.models import SkillContext
from .models import CharacterCard

async def execute(input_data: Dict[str, Any], context: SkillContext) -> Dict[str, Any]:
    card_data = input_data.get("card_data")
    
    if not card_data:
        return {"valid": False, "error": "Missing required parameter: card_data"}

    try:
        card = CharacterCard.model_validate(card_data)
        return {"valid": True, "card": card.model_dump()}
    except Exception as e:
        return {"valid": False, "error": str(e)}
