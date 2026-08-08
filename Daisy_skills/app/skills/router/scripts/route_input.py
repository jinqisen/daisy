from typing import Dict, Any
from runtime.models import SkillContext
from app.skills.router.scripts.intelligent_router import intelligent_router

async def execute(input_data: Dict[str, Any], context: SkillContext) -> Dict[str, Any]:
    user_input = input_data.get("user_input")
    user_id = input_data.get("user_id")
    session_id = input_data.get("session_id")
    router_context = input_data.get("context", {})
    
    if not all([user_input, user_id, session_id]):
        return {
            "error": "Missing required parameters: user_input, user_id, session_id"
        }
        
    result = await intelligent_router.route_input(
        user_input=user_input,
        user_id=user_id,
        session_id=session_id,
        context=router_context
    )
    
    return result.model_dump()
