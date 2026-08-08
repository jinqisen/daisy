from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import structlog
import asyncio
import json
import re

from app.core.config import settings
from app.core.constants import ORDERED_EMOTIONS, DEFAULT_PERSONALITY, PERSONALITY_TYPES
from app.core.llm import get_llm_service
from app.services.learning.rl_agent import get_rl_agent

logger = structlog.get_logger()

# 标准情感标签（Ekman 7类 或 GoEmotions 28类）
# 我们必须使用固定的顺序作为 RL 输入向量
# ORDERED_EMOTIONS 已从 constants 导入

class SelectionResult(BaseModel):
    """个性选择策略的统一结果结构"""
    selected_personality: str
    personality_weights: Dict[str, float]
    target_emotion: Optional[Dict[str, float]] = None # 策略建议的目标情感向量 (Ekman 7)
    reasoning: str
    metadata: Dict[str, Any] = {} # 日志/UI 的额外信息

class Strategy(ABC):
    @abstractmethod
    async def select_personality(self, state: Dict[str, Any], user_settings: Any = None) -> SelectionResult:
        pass

class LLMStrategy(Strategy):
    """
    使用 LLM 专家代理（心理学家）分析上下文和情绪。
    有利于可解释性和细致的理解。
    """
    async def select_personality(self, state: Dict[str, Any], user_settings: Any = None) -> SelectionResult:
        text = state["user_input"]
        user_id = state.get("user_id")
        trigger_message_id = state.get("user_message_id")
        # 尝试从 trace 中获取合并的上下文（如果可用）
        context_text = text
        trace = state.get("workflow_trace", {})
        if "analyze" in trace and "input" in trace["analyze"]:
            context_text = trace["analyze"]["input"].get("merged_context_text", text)
        
        top_emotions = state.get("top_emotions", [])
        
        # 构建提示
        llm = get_llm_service()
        
        from app.prompts.templates import get_strategy_selection_prompt, get_strategy_selection_system_prompt
        prompt = get_strategy_selection_prompt(context_text, top_emotions)
        
        try:
            response = ""
            if hasattr(llm, "generate_response_async"):
                response = await llm.generate_response_async(
                    system_prompt=get_strategy_selection_system_prompt(),
                    user_input=prompt,
                    context="",
                    user_settings=user_settings,
                    metadata={
                        "trigger_message": text,
                        "agent_name": "StrategyAgent",
                        "user_id": user_id,
                        "trigger_message_id": trigger_message_id,
                        # 记入本次执行的预算账本(见 core/budget.py);
                        # 不带 execution_id 的调用不计数,上限就成了假保护
                        "execution_id": state.get("execution_id"),
                        # 内部 JSON 分类任务,强制轻量模型(与 Router/ReAct 同策略)。
                        # 实测该节点用重模型 p50≈22-28s,是端到端延迟的最大单项。
                        # 用 force_lightweight 而非 route:route 会污染 by_route 路由分布统计
                        "force_lightweight": True
                    }
                )
            else:
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None,
                    llm.generate_response,
                    get_strategy_selection_system_prompt(),
                    prompt,
                    "",
                    user_settings,
                    {
                        "trigger_message": text,
                        "agent_name": "StrategyAgent",
                        "user_id": user_id,
                        "trigger_message_id": trigger_message_id,
                        # 记入本次执行的预算账本(见 core/budget.py);
                        # 不带 execution_id 的调用不计数,上限就成了假保护
                        "execution_id": state.get("execution_id"),
                        "force_lightweight": True
                    }
                )
            
            # 解析 JSON
            try:
                match = re.search(r'\{.*\}', response, re.DOTALL)
                if match:
                    json_str = match.group(0)
                    result = json.loads(json_str)
                else:
                    result = json.loads(response)
            except json.JSONDecodeError as e:
                # 如果 JSON 失败，直接抛出异常
                logger.error("LLM Strategy: Failed to parse JSON.")
                raise e

            best_match = result.get("best_match", DEFAULT_PERSONALITY)
            weights = result.get("weights", {})
            target_emotion = result.get("target_emotion", {})
            reasoning = result.get("reasoning", "无法生成分析")
            
            # 归一化
            normalized_weights = self._normalize_weights(weights)
            
            # UI 元数据
            metadata = {
                "title": "Communication Analysis (LLM Expert)",
                "content": {
                    "input_context": context_text,
                    "top_emotions": top_emotions,
                    "best_match": best_match,
                    "weights": normalized_weights,
                    "target_emotion": target_emotion,
                    "reasoning": reasoning,
                    "prompt": prompt
                },
                "timestamp": None # 如果需要，将由调用者添加
            }

            return SelectionResult(
                selected_personality=best_match,
                personality_weights=normalized_weights,
                target_emotion=target_emotion,
                reasoning=reasoning,
                metadata=metadata
            )

        except Exception as e:
            logger.error(f"LLM Strategy failed: {e}")
            raise e

    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        required_keys = PERSONALITY_TYPES
        normalized = {k: weights.get(k, 0.0) for k in required_keys}
        total = sum(normalized.values())
        if total > 0:
            normalized = {k: v/total for k, v in normalized.items()}
        else:
            normalized = {k: 1.0/len(required_keys) for k in required_keys}
        return normalized

class RLStrategy(Strategy):
    """
    使用强化学习代理根据情绪向量选择个性。
    快速且可训练，但最初的可解释性较差。
    """
    async def select_personality(self, state: Dict[str, Any], user_settings: Any = None) -> SelectionResult:
        try:
            # 1. 构建状态向量
            emotion_scores = state.get("emotion_scores", {})
            ekman_scores = state.get("ekman_scores", {})
            
            # 决定使用哪个分数源
            # 如果配置的是 Ekman 7类 (长度为7)，且 state 中有 ekman_scores (聚合后的分数)，则优先使用
            source_scores = emotion_scores
            if len(ORDERED_EMOTIONS) == 7 and ekman_scores:
                source_scores = ekman_scores
            
            # 向量化
            vector = []
            for emotion in ORDERED_EMOTIONS:
                vector.append(source_scores.get(emotion, 0.0))
            
            # 如果长度不足，用 0.0 填充（防御性编程）
            if len(vector) < len(ORDERED_EMOTIONS):
                vector.extend([0.0] * (len(ORDERED_EMOTIONS) - len(vector)))
            
            # 注意: RLAgent 期望的输入维度必须与模型训练时一致
            # 当前配置为: RL_STATE_DIM
            
            user_id = state.get("user_id", "default")
            
            # 2. 调用代理 (推理)
            # RLAgent.select_action 是同步的且快速 (CPU 推理)
            agent = get_rl_agent(user_id=user_id)
            
            action_result = agent.select_action(vector)
            
            best_match = action_result["personality"]
            weights = action_result["weights"]
            
            # RL 不会生成文本推理，所以我们合成一个或保留通用的
            reasoning = f"基于强化学习模型推荐 (Action Index: {action_result['action_idx']})。根据当前情感状态向量，模型预测【{best_match}】风格能获得最大长期奖励。"
            
            metadata = {
                "title": "Communication Analysis (RL Model)",
                "content": {
                    "input_vector_preview": vector[:5],
                    "best_match": best_match,
                    "weights": weights,
                    "reasoning": reasoning,
                    "model_user_id": user_id
                }
            }
            
            return SelectionResult(
                selected_personality=best_match,
                personality_weights=weights,
                target_emotion={}, # RL 暂未实现 target_emotion
                reasoning=reasoning,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"RL Strategy failed: {e}")
            raise e

class StrategyService:
    def __init__(self):
        self.strategies = {
            "llm": LLMStrategy(),
            "rl": RLStrategy()
        }
    
    def get_strategy(self, mode: str) -> Strategy:
        return self.strategies.get(mode, self.strategies["llm"])

# Singleton
_strategy_service = StrategyService()

def get_strategy_service() -> StrategyService:
    return _strategy_service
