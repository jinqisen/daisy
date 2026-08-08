from typing import Dict, Any, Optional
from runtime.models import SkillContext
from .generator import character_generator

async def execute(input_data: Dict[str, Any], context: SkillContext) -> Dict[str, Any]:
    name = input_data.get("name")
    gender = input_data.get("gender")
    age = input_data.get("age")
    occupation = input_data.get("occupation")
    backstory = input_data.get("backstory", "")
    world_setting = input_data.get("world_setting", "Modern Realism")
    avatar_path = input_data.get("avatar_path")

    if not all([name, gender, age, occupation]):
         return {"error": "Missing required parameters: name, gender, age, occupation"}

    card = await character_generator.generate_deep_card(
        name=name,
        gender=gender,
        age=age,
        occupation=occupation,
        backstory=backstory,
        world_setting=world_setting,
        avatar_path=avatar_path
    )
    if card:
        return card.model_dump()
    return {"error": "Failed to generate character card"}
