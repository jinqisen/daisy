from typing import TypedDict, List, Dict, Any, Optional

class AgentState(TypedDict):
    """
    Agent State Definition for Daisy Skills
    """
    user_input: str
    user_id: str
    session_id: Optional[str]
    conversation_id: Optional[str]
    route: str
    emotion_data: Optional[Dict[str, Any]]
    
    chat_history: List[Any]
    
    response: str
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    
    next_step: str
