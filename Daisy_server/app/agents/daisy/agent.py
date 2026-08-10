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
        
        emotion_desc = (
            f"情绪偏向 {emotion['label']}（强度 {emotion['score']}）"
            if emotion and isinstance(emotion, dict) else "无明显情绪波动"
        )

        # 角色设定:主动关心必须和主对话是同一个人。
        # 原实现完全不读角色卡,提示词里写死 "You are Daisy" 且整段英文 ——
        # 实测发出的主动消息是英文,而角色是中文人设(静雯)。
        persona = context.get("common_settings")
        persona_name = getattr(persona, "name", None) or self.name
        
        # 走 core 的 PromptLoader,而不是 prompts.templates ——
        # agents 是 L1,prompts 是 L2,反向 import 会破坏依赖方向(护栏已实测拦下)。
        # 本文件上方的 system prompt 也是同一写法。
        prompt = PromptLoader.get_instance().render(
            "get_proactive_trigger_prompt",
            persona_name=persona_name,
            persona_gender=getattr(persona, "gender", "") or "",
            relationship=getattr(persona, "relationship", "") or "",
            backstory=(getattr(persona, "backstory", "") or "")[:400],
            current_time=datetime.datetime.now().strftime("%H:%M"),
            emotion_desc=emotion_desc,
            history_str=history_str or "（还没有聊过）",
        )

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
