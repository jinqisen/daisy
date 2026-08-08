import re
from typing import Dict, Any, Awaitable, Callable, Optional
import structlog

logger = structlog.get_logger()

class IntelligentRouter:
    def __init__(self, judge: Optional[Callable[[Dict[str, Any]], Awaitable[str]]] = None):
        # Regex patterns for FAST path (Simple greetings, confirmations)
        self.fast_patterns = [
            r'^(好|嗯|是|对|行|可以)[啊呀的吗]*[！!。.]*$', 
            r'^(早|早安|早上好|晚安)[！!。.]*$',
            r'^(你好|嗨|哈喽|在吗|在不在|吃了吗|睡了吗)[！!。.]*$',
            r'^(谢谢|谢了|OK|Ok|ok|好的|收到|行吧|可以呀)[！!。.]*$',
            r'^(👍|👌|🙏)[！!。.]*$'
        ]
        self._judge = judge

    async def route(self, state: Dict[str, Any]) -> str:
        user_input = state.get('user_input', '')
        if not user_input:
            return "STANDARD"

        # Step 1: Rule Matching
        for pattern in self.fast_patterns:
            if re.match(pattern, user_input.strip()):
                logger.info("Router decision: FAST (Rule Match)", user_input=user_input)
                return "FAST"

        if not self._judge:
            return "STANDARD"

        # Step 2: LLM Judge
        # No fallback allowed. Exception must propagate.
        decision = await self._judge(state)
        decision = (decision or "STANDARD").strip().upper()

        final_decision = "DEEP" if "DEEP" in decision else "STANDARD"
        logger.info(f"Router decision: {final_decision} (Judge)", user_input=user_input)
        return final_decision
