import datetime
import structlog
import hashlib
from typing import Any, Callable
from ..capability import essential, enhancement
from ...core.config import settings
from ...services.persona.strategy import get_strategy_service
from ...core.cache import cache_result
from ...core.exceptions import NodeError
from .state import AgentState
from .tools import add_trace, get_common_settings_async, monitor_execution_time

logger = structlog.get_logger()

def style_cache_key_builder(*args, **kwargs) -> str:
    """
    Generate a cache key for communication style analysis.
    Key depends on:
    1. User ID (implies Role Settings)
    2. User Input (Hash)
    3. Emotions (Hash)
    
    Compatible with decorator which passes *args, **kwargs
    """
    try:
        # Extract 'state' from args or kwargs
        state = kwargs.get('state')
        if not state and args:
            # Assuming state is the first positional argument
            state = args[0]
            
        if not state or not isinstance(state, dict):
            # Fallback if state extraction fails
            return f"style_analysis:error:no_state:{datetime.datetime.now().timestamp()}"

        user_id = str(state.get("user_id", "unknown"))
        user_input = str(state.get("user_input", ""))
        emotions = state.get("top_emotions", [])
        
        # Ensure emotions is a list
        if not isinstance(emotions, list):
            emotions = []
        
        # Hash input and emotions
        input_hash = hashlib.md5(user_input.encode("utf-8", errors="ignore")).hexdigest()
        emotions_str = str(sorted([str(e) for e in emotions])) # Sort to ensure stability
        emotions_hash = hashlib.md5(emotions_str.encode("utf-8", errors="ignore")).hexdigest()
        
        return f"style_analysis:{user_id}:{input_hash}:{emotions_hash}:v2"
    except Exception as e:
        logger.error(f"Cache key generation failed: {e}")
        # Fallback key to avoid caching errors (use random or timestamp to force refresh)
        return f"style_analysis:error:{datetime.datetime.now().timestamp()}"

@enhancement(fallback={})
@monitor_execution_time
@cache_result(ttl=3600, key_builder=style_cache_key_builder)
async def analyze_communication_style(state: AgentState) -> AgentState:
    """
    节点：沟通风格分析 (策略模式)
    根据配置 (LLM vs RL) 选择相应策略来确定沟通风格
    """
    user_id = state["user_id"]
    common = await get_common_settings_async(user_id)
    
    mode = settings.PERSONALITY_SELECTION_MODE
    strategy_service = get_strategy_service()
    strategy = strategy_service.get_strategy(mode)
    
    logger.info(f"执行沟通策略: {mode.upper()}")
    
    try:
        result = await strategy.select_personality(state, user_settings=common)
        
        # 补全 timestamp 并准备 UI 数据
        ui_data = result.metadata.copy()
        if "timestamp" not in ui_data or not ui_data["timestamp"]:
             ui_data["timestamp"] = datetime.datetime.now().isoformat()

        # 记录 (context, action) 供 bandit/RL 离线评估。
        # 只记录、不改变决策 —— 线上仍用上面选出的 result。奖励在下一轮
        # Reflexion 结算 S 时配对(见 services/rl_dataset.py)。
        try:
            from ...services.learning.rl_dataset import build_context_vector, record_decision
            from ...services.persona.character_card import infer_relationship_stage
            ctx_state = dict(state)
            ctx_state["relationship_stage"] = infer_relationship_stage(
                getattr(common, "relationship", None) if common else None
            )
            await record_decision(
                session_id=state.get("session_id", ""),
                user_id=state.get("user_id"),
                context=build_context_vector(ctx_state),
                action=result.selected_personality,
                action_weights=result.personality_weights,
                policy=mode,
            )
        except Exception as e:
            logger.warning(f"RL dataset: record_decision skipped: {e}")

        # 更新 Trace
        trace = await add_trace(state, "analyze_communication_style",
            input_data={
                "mode": mode,
                "emotions_preview": str(state.get("top_emotions", []))[:100]
            },
            output_data={
                "best_match": result.selected_personality, 
                "weights": result.personality_weights,
                "reasoning": result.reasoning,
                "ui_card_data": ui_data
            }
        )

        return {
            "selected_personality": result.selected_personality,
            "personality_weights": result.personality_weights,
            "target_emotion": result.target_emotion, # Pass to State
            "love_style_weights": {
                "best_match": result.selected_personality,
                "weights": result.personality_weights,
                "reasoning": result.reasoning
            },
            "workflow_trace": trace
        }
        
    except Exception as e:
        logger.error(f"策略执行失败: {e}")
        raise NodeError("CommunicationStyle", e)
