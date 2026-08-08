from typing import Dict, Any
from runtime.models import SkillContext
from .service import reflexion_service


async def execute(input_data: Dict[str, Any], context: SkillContext) -> Dict[str, Any]:
    user_id = input_data.get("user_id")
    session_id = input_data.get("session_id")
    user_input = input_data.get("user_input", "")
    agent_response = input_data.get("agent_response", "")
    agent_emotion = input_data.get("agent_emotion", {})
    target_emotion = input_data.get("target_emotion", {})
    user_emotion = input_data.get("user_emotion", {})
    history = input_data.get("history", [])
    response_time_sec = input_data.get("response_time_sec")
    user_feedback = input_data.get("user_feedback")
    
    if not user_id or not session_id:
        return {
            "success": False,
            "message": "Missing required parameters: user_id and session_id"
        }
    
    result = await reflexion_service.enqueue_event(
        user_id=user_id,
        session_id=session_id,
        user_input=user_input,
        agent_response=agent_response,
        agent_emotion=agent_emotion,
        target_emotion=target_emotion,
        user_emotion=user_emotion,
        history=history,
        response_time_sec=response_time_sec,
        user_feedback=user_feedback
    )
    
    return result
