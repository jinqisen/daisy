from typing import Dict, Any
from runtime.models import SkillContext
from app.skills.reflexion.scripts.service import reflexion_service


async def execute(input_data: Dict[str, Any], context: SkillContext) -> Dict[str, Any]:
    query_text = input_data.get("query_text", "")
    limit = input_data.get("limit", 3)
    user_id = input_data.get("user_id")
    
    if not query_text:
        return {
            "success": False,
            "message": "Missing required parameter: query_text"
        }
    
    result = await reflexion_service.retrieve_exemplars(
        query_text=query_text,
        limit=limit,
        user_id=user_id
    )
    
    return result
