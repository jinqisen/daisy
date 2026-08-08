from typing import Dict, Any
from runtime.models import SkillContext
from .generator import character_generator
from .models import CharacterCard

async def execute(input_data: Dict[str, Any], context: SkillContext) -> Dict[str, Any]:
    card_data = input_data.get("card_data")
    route = input_data.get("route")
    user_input = input_data.get("user_input")
    relationship_stage = input_data.get("relationship_stage")

    if not card_data:
        return {"error": "Missing required parameter: card_data"}

    try:
        card = CharacterCard.model_validate(card_data)
        addendum = character_generator.build_prompt_addendum(
            card=card,
            route=route,
            user_input=user_input,
            relationship_stage=relationship_stage
        )
        return {"addendum": addendum}
    except Exception as e:
        return {"error": f"Failed to build prompt addendum: {str(e)}"}
