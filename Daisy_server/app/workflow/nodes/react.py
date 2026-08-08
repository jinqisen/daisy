import asyncio
import json
from langchain_core.messages import SystemMessage, HumanMessage
from ..capability import essential, enhancement
from ...core.llm import get_llm_service
from .state import AgentState
from .tools import add_trace, monitor_execution_time
from ...services.dialogue.tools import AVAILABLE_TOOLS, get_tool_descriptions
from ...core.config import settings
from ...core.exceptions import NodeError
import structlog

logger = structlog.get_logger()

@enhancement(fallback={"tool_results": {}})
@monitor_execution_time
async def tool_check(state: AgentState) -> AgentState:
    """
    Node: Tool Check
    Decide if tools are needed.
    """
    user_input = state["user_input"]
    if state.get("route") != "DEEP":
        return {"tool_results": {}}
    
    # 1. Check if we have tools
    if not AVAILABLE_TOOLS:
        return {"tool_results": {}}

    llm_service = get_llm_service()
    llm = llm_service.get_deep_llm()
    if not llm:
        return {"tool_results": {}}

    tool_results = {}
    steps = []
    max_chars = settings.TOOL_RESULT_MAX_CHARS
    try:
        max_steps = settings.DEEP_TOOL_MAX_STEPS
        allowed_tools = {name for name in settings.DEEP_ALLOWED_TOOLS if name in AVAILABLE_TOOLS}
        allowed_desc = "\n".join(
            f"- {AVAILABLE_TOOLS[name].name}: {AVAILABLE_TOOLS[name].description}" for name in sorted(allowed_tools)
        )
        for i in range(max_steps):
            # 预算控制点(core/budget.py):本轮执行超出配置上限时停止工具探索,
            # 已获得的 tool_results 照常返回,主生成不受影响(降级而非失败)
            from ...core.budget import is_over_budget
            over, reason = await is_over_budget(state.get("execution_id"))
            if over:
                steps.append({"budget_stop": reason})
                logger.warning("Tool loop stopped by execution budget", reason=reason)
                break

            observation_text = ""
            if tool_results:
                pairs = []
                for name, res in tool_results.items():
                    pairs.append(f"- {name}: {str(res)[:max_chars]}")
                observation_text = "\n".join(pairs)

            prompt = f"""
You decide whether to call an external tool.

Available Tools:
{allowed_desc if allowed_desc else "(none)"}

User Input: "{user_input}"

Current Observations:
{observation_text if observation_text else "(none)"}

Output JSON only:
{{"tool": "tool_name_or_null", "query": "query_if_any"}}
"""

            response = await asyncio.wait_for(
                llm.ainvoke(
                    [SystemMessage(content="Output valid JSON only."), HumanMessage(content=prompt)],
                    config={"response_format": {"type": "json_object"}},
                ),
                timeout=settings.DEEP_TOOL_STEP_TIMEOUT_SEC,
            )

            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()

            decision = json.loads(content)
            tool_name = decision.get("tool")
            tool_query = decision.get("query")
            steps.append({"decision": decision})

            if not tool_name:
                break

            if tool_name not in allowed_tools:
                steps.append({"error": f"unknown_tool:{tool_name}"})
                break

            tool = AVAILABLE_TOOLS[tool_name]
            try:
                result = await tool.run(tool_query)
            except Exception as tool_err:
                # 单个工具不可用(如未配置搜索密钥)只跳过它,绝不能中断对话。
                # 原实现让异常一路冒泡:缺一把**可选**的工具密钥 → tool_check 抛
                # NodeError → 整个 chat_task 挂掉 → 消息永远卡在 pending,
                # 用户之后每次点发送都会重放这条旧消息。
                logger.warning(f"Tool '{tool_name}' unavailable, skipping: {tool_err}")
                steps.append({"tool": tool_name, "query": tool_query, "error": str(tool_err)})
                break
            tool_results[tool_name] = str(result)[:max_chars]
            steps.append({"tool": tool_name, "query": tool_query, "result": result})

        trace = await add_trace(
            state,
            "tool_check",
            input_data={"route": state.get("route"), "user_input": user_input},
            output_data={"tool_results": tool_results, "steps": steps},
        )

        return {"tool_results": tool_results, "workflow_trace": trace}
            
    except Exception as e:
        # 工具探索是**增强**能力,不是对话的必要条件 —— 失败必须降级而非中断。
        # 原实现 raise NodeError,会让整个 chat_task 挂掉、消息永久 pending。
        logger.warning(f"Tool check degraded (continuing without tools): {e}")
        try:
            trace = await add_trace(
                state,
                "tool_check",
                input_data={"route": state.get("route"), "user_input": user_input},
                output_data={"tool_results": {}, "error": str(e)},
            )
            return {"tool_results": {}, "workflow_trace": trace}
        except Exception:
            return {"tool_results": {}}
