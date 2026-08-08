import json
import structlog
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from app.services.llm import get_llm_service

logger = structlog.get_logger()

class RouteResult(BaseModel):
    route: str = Field(..., description="路由结果: FAST/STANDARD/DEEP")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    reasoning: str = Field(..., description="决策理由")

class RouteJudge:
    def __init__(self):
        self.llm = get_llm_service()
        
    async def judge_route(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None
    ) -> RouteResult:
        system_prompt = """
# Role: Dialogue Complexity Analyzer
你是一个对话复杂度分析专家。你的任务是分析用户输入，并将其路由到三个处理路径之一：STANDARD 或 DEEP。
(FAST 路径由正则处理，不需要你判断)

# Routing Criteria

## STANDARD (标准响应)
- 适用场景：日常闲聊、简单问答、情感安抚、不需要复杂推理的任务。
- 特征：输入简短，意图明确，不需要多步思考。
- 示例："今天天气怎么样？"、"我有点累。"、"讲个笑话。"

## DEEP (深度处理)
- 适用场景：复杂角色扮演、逻辑推理、创意写作、多步任务、需要深度情感共鸣。
- 特征：输入较长，包含多个指令，或者涉及复杂的背景设定。
- 示例："假设你是一个古代剑客，我们在客栈相遇..."、"分析这首诗的意境。"、"帮我制定一个详细的减肥计划。"

# Output Format
你必须输出一个 JSON 对象，不要包含 markdown 格式。
{
  "route": "STANDARD" | "DEEP",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<short explanation>"
}
"""
        user_content = f"User Input: {user_input}"
        if context:
            user_content += f"\nContext: {json.dumps(context, ensure_ascii=False)}"

        try:
            response_text = await self.llm.generate_response_async(
                system_prompt=system_prompt,
                user_input=user_content,
                metadata={"agent_name": "RouteJudge"}
            )
            
            # Clean up potential markdown formatting
            json_str = response_text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
                
            data = json.loads(json_str)
            return RouteResult(**data)
            
        except Exception as e:
            logger.error(f"Route judge failed: {e}")
            # Fallback to STANDARD on error
            return RouteResult(
                route="STANDARD", 
                confidence=0.5, 
                reasoning=f"Fallback due to error: {str(e)}"
            )

route_judge = RouteJudge()
