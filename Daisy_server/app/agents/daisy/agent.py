from typing import Dict, Any, Optional
import json
import datetime
import structlog
from ..base import BaseAgent
from .config import CommonSettings
from ...core.prompt_loader import PromptLoader
from ...core.llm import get_llm_service

logger = structlog.get_logger()

class DaisyAgent(BaseAgent):
    def __init__(self):
        self._name = "Daisy"

    @property
    def name(self) -> str:
        return self._name

    @property
    def config(self) -> Dict[str, Any]:
        return CommonSettings().dict()

    async def get_system_prompt(self, context: Dict[str, Any]) -> str:
        """
        Generate system prompt using CommonSettings from context.
        """
        common = context.get("common_settings")
        
        # Handle case where common might be None or missing
        core_system_prompt = None
        if common:
            # Check if it's a dict or object
            if isinstance(common, dict):
                core_system_prompt = common.get("core_system_prompt")
            elif hasattr(common, "core_system_prompt"):
                core_system_prompt = common.core_system_prompt
        
        # Use PromptLoader to render the template
        return PromptLoader.get_instance().render(
            "get_core_system_instructions",
            core_system_prompt=core_system_prompt
        )

    async def check_proactive_trigger(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Daisy-specific proactive logic.
        """
        history_str = context.get("history", "")
        emotion = context.get("emotion") # Dict: {label, score}
        
        llm_service = get_llm_service()
        llm = llm_service.get_llm()
        
        if not llm:
            logger.error("Failed to initialize LLM for proactive evaluation")
            return {"should_act": False, "reason": "LLM not available"}
        
        emotion_desc = f"User is feeling {emotion['label']} (intensity: {emotion['score']})" if emotion and isinstance(emotion, dict) else "User state is normal."
        
        # Hardcoded prompt extracted from ProactiveService
        prompt = f"""
        You are Daisy, a proactive AI companion.
        
        Current Context:
        Time: {datetime.datetime.now().strftime("%H:%M")}
        User Emotion: {emotion_desc}
        Recent Chat History:
        {history_str}
        
        Task:
        Decide if you should initiate a conversation with the user NOW.
        
        Guidelines:
        1. If the user is emotional (sad/lonely), be supportive and gentle.
        2. If routine, try to find a topic or greeting based on the time. Don't be too passive.
        3. Avoid being annoying, but a friendly check-in after silence is often welcome.
        4. If you decide to act, generate a SHORT, natural opening message (max 1 sentence).
        
        Output Format (JSON):
        {{
            "score": <0-10, 7+ means act>,
            "reason": "<why you decided this>",
            "content": "<message content if score >= 7, else empty>"
        }}
        """
        
        try:
            response = await llm.ainvoke(prompt)
            content = response.content.strip()
            
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
                
            data = json.loads(content)
            
            if data.get("score", 0) >= 7:
                return {"should_act": True, "content": data.get("content"), "reason": data.get("reason")}
            else:
                return {"should_act": False, "reason": data.get("reason")}
                
        except Exception as e:
            logger.error(f"LLM evaluation failed: {e}")
            return {"should_act": False, "reason": f"Error: {str(e)}"}
