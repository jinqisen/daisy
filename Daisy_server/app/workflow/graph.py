from langgraph.graph import StateGraph, END
from .nodes import (
    AgentState,
    analyze_emotion,
    retrieve_memory,
    # select_personality, # Removed
    analyze_communication_style, # New Expert Node
    summarize_topic,    # Task 4 Independent Node
    ensure_portrait,    # Task 1 Independent Node
    analyze_style,      # Task 2 Independent Node
    agent_thoughts,     # Task 3 Independent Node
    # consult_agents, # Merged into generate
    generate_response,
    save_memory_and_log,
    fast_generate,
    standard_generate,
    tool_check,
    correct_typo
)
from ..services.dialogue.router import IntelligentRouter
from ..core.smart_cache import cache_node
from ..core.redis import redis_client
from ..core.metrics import bucket_label, ROUTER_HIST_THRESHOLDS_MS
import hashlib
import time


async def _judge_route_llm(state: AgentState) -> str:
    from langchain_core.messages import SystemMessage, HumanMessage
    from ..core.llm import LLMService

    user_input = state.get("user_input", "")

    prompt = f"""
    Analyze the following user input and determine the complexity of the response required.

    User Input: "{user_input}"

    Classify into one of the following categories:
    - STANDARD: Only for extremely simple, non-emotional, or purely functional messages (e.g., "OK", "Bye", "Yes", "No", "Thanks"). This path is faster but lacks personality and emotional depth.
    - DEEP: For ALL roleplay, emotional conversation, storytelling, personal sharing, or queries requiring factual knowledge. This is the DEFAULT path to maintain character soul and high-quality interaction.

    Unless the input is a trivial one-word confirmation or greeting, ALWAYS choose DEEP.
    """

    from ..core.exceptions import NodeError
    
    try:
        llm = LLMService().get_lightweight_llm()
    except Exception as e:
        raise NodeError("Router", e)

    response = await llm.ainvoke(
        [
            SystemMessage(content="You are a routing assistant. Classify the user input complexity."),
            HumanMessage(content=prompt),
        ]
    )
    return getattr(response, "content", "")


router = IntelligentRouter(judge=_judge_route_llm)


def route_cache_key_builder(state: AgentState) -> str:
    raw_key = "|".join(
        [
            str(state.get("user_id", "unknown")),
            str(state.get("session_id", "no-session")),
            str(state.get("user_input", "")),
        ]
    )
    return hashlib.md5(raw_key.encode()).hexdigest()

@cache_node(
    key_prefix="router",
    ttl=600,
    key_builder=route_cache_key_builder,
)
async def route_logic(state: AgentState):
    start_ts = time.time()
    from ..core.utils import is_offline_meetup_intent
    if is_offline_meetup_intent(state.get("user_input", "")):
        decision = "DEEP"
    else:
        decision = await router.route(state)
    state["route"] = decision
    duration_ms = int((time.time() - start_ts) * 1000)
    try:
        if redis_client.enabled and redis_client.redis:
            await redis_client.redis.incr("metrics:router:count")
            await redis_client.redis.incrby("metrics:router:sum_ms", duration_ms)
            await redis_client.redis.hincrby("metrics:router:by_route", decision, 1)
            await redis_client.redis.hincrby("metrics:router:hist", bucket_label(duration_ms, ROUTER_HIST_THRESHOLDS_MS), 1)
    except Exception:
        pass
    return decision

def should_continue_generation(state: AgentState) -> str:
    """
    检查生成节点是否因为缺少依赖而跳过
    如果跳过，则结束当前分支 (END)
    如果成功，则继续保存 (save)
    """
    if state.get("_skip_generation", False):
        return END
    return "save"

def create_graph():
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("analyze", analyze_emotion)
    workflow.add_node("retrieve", retrieve_memory)
    # workflow.add_node("select_persona", select_personality) # 跳过，支持专家代理（功能已移除）
    workflow.add_node("analyze_communication_style", analyze_communication_style) # 新的专家节点
    workflow.add_node("summarize_topic", summarize_topic)       # 任务 4
    workflow.add_node("ensure_portrait", ensure_portrait)       # 任务 1
    workflow.add_node("analyze_style", analyze_style)           # 任务 2
    workflow.add_node("agent_thoughts", agent_thoughts)         # 任务 3
    # workflow.add_node("consult", consult_agents)
    workflow.add_node("generate", generate_response)
    workflow.add_node("save", save_memory_and_log)
    workflow.add_node("fast_generate", fast_generate)
    workflow.add_node("standard_generate", standard_generate)
    workflow.add_node("tool_check", tool_check)

    # 定义边
    # 路由 (入口点)
    workflow.set_conditional_entry_point(
        route_logic,
        {
            "FAST": "fast_generate",
            "STANDARD": "standard_generate",
            "DEEP": "analyze"
        }
    )
    
    # Fast Path
    workflow.add_edge("fast_generate", "save")
    workflow.add_edge("standard_generate", "save")

    # 从分析开始的并行分支
    # 分支 1: 分析 -> 分析沟通风格 (依赖于情感)
    workflow.add_edge("analyze", "analyze_communication_style")
    
    # 分支 2: 分析 -> 检索 (独立，只需要输入)
    workflow.add_edge("analyze", "retrieve")
    
    # 分支 3: 分析 -> 总结话题 (独立任务 4)
    workflow.add_edge("analyze", "summarize_topic")
    
    # 分支 4: 分析 -> 确保画像 (独立任务 1)
    workflow.add_edge("analyze", "ensure_portrait")
    
    # 分支 5: 分析 -> 工具检查 (Task 2.2 ReAct)
    workflow.add_edge("analyze", "tool_check")

    # 第二层：基于分析结果的任务
    # 风格分析 (Task 2): 依赖沟通风格
    workflow.add_edge("analyze_communication_style", "analyze_style")
    
    # 角色思考 (Task 3): 依赖沟通风格、话题总结、画像
    workflow.add_edge("analyze_communication_style", "agent_thoughts")
    workflow.add_edge("summarize_topic", "agent_thoughts")
    workflow.add_edge("ensure_portrait", "agent_thoughts")
    
    # 汇聚到生成
    # generate 依赖: analyze_style, agent_thoughts, retrieve
    workflow.add_edge("analyze_style", "generate")
    workflow.add_edge("agent_thoughts", "generate")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("tool_check", "generate")

    # 生成 -> 保存 (条件)
    workflow.add_conditional_edges(
        "generate",
        should_continue_generation,
        {
            END: END,
            "save": "save"
        }
    )
    
    # 保存 -> 结束
    workflow.add_edge("save", END)

    return workflow.compile()

app_graph = create_graph()
