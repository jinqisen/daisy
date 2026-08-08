from typing import Dict, Any
from runtime.models import SkillContext
from .service import reflexion_service


async def execute(input_data: Dict[str, Any], context: SkillContext) -> Dict[str, Any]:
    user_id = input_data.get("user_id")
    session_id = input_data.get("session_id")
    
    if not user_id:
        return {
            "success": False,
            "message": "Missing required parameter: user_id"
        }
    
    result = await reflexion_service.get_metrics(
        user_id=user_id,
        session_id=session_id
    )
    
    return result
