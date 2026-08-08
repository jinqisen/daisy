import asyncio
import datetime
import time
import uuid
import structlog
from ..capability import essential, enhancement
from ...core.config import settings
from ...core.constants import (
    ENGAGEMENT_LENGTH_THRESHOLD,
    ENGAGEMENT_WEIGHT_INTENSITY,
    ENGAGEMENT_WEIGHT_AROUSAL,
    ENGAGEMENT_WEIGHT_LENGTH
)
from ...services.persona.emotion import get_emotion_service
from ...services.learning.reflexion.metrics import metrics_service
from .state import AgentState
from .tools import add_trace, get_common_settings_async, monitor_execution_time
from ...services.memory.chat_history import history_service
from ...core.exceptions import NodeError

logger = structlog.get_logger()

@essential
@monitor_execution_time
async def analyze_emotion(state: AgentState) -> AgentState:
    """
    节点：情感分析
    分析用户输入的情感，计算投入度，并处理上下文窗口
    """
    try:
        text = state["user_input"]
        session_id = state["session_id"]
        if "request_start_ts" not in state:
            state["request_start_ts"] = time.time()
        
        # 0. 初始化 execution_id (如果尚未存在)
        if "execution_id" not in state:
            state["execution_id"] = str(uuid.uuid4())

        # 1. 启动追踪 (显式开始节点)
        # 因为这是入口点，如果 trace 尚未初始化，则在此处初始化
        trace = state.get("workflow_trace", {})
        if not trace:
            # 使用 __start__ 匹配 LangGraph 内部的开始节点 ID 以便可视化
            trace = await add_trace(state, "__start__", 
                input_data={
                    "session_id": session_id,
                    "user_id": state["user_id"],
                    "execution_id": state["execution_id"],
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
                },
                output_data={
                    "user_input": text,
                    "status": "started"
                }
            )
            # 临时更新 state，以便后续的 add_trace 调用能看到它
            state["workflow_trace"] = trace

        # 2. 上下文合并策略 (带窗口限制)
        # 获取最近的用户消息，为短输入提供更好的上下文
        context_text = ""
        try:
            # 架构调整：基于时间窗口获取最近历史 (最近 1 小时即可，情感分析不需要太久)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
                
            def fetch_recent_context():
                 # 获取最近 1 小时的消息，作为情感分析的上下文
                 recent_msgs = history_service.get_recent_history_by_time(
                     state["user_id"], 
                     days=0.04, # ~1 hour
                     exclude_statuses=["pending", "processing", "failed"]
                 )
                 # 只取最近的 N 条 (settings.EMOTION_CONTEXT_TURNS)
                 return [m.content for m in recent_msgs[-settings.EMOTION_CONTEXT_TURNS:]]

            msgs = await loop.run_in_executor(None, fetch_recent_context)
            
            # 过滤掉当前正在处理的消息（因为它已经被预存到数据库中了，会出现在 history 的最后）
            # 避免在 full_text = context + text 时重复
            if msgs and msgs[-1] == text:
                msgs.pop()
                
            if msgs:
                context_text = " ".join(msgs)
        except Exception as e:
            logger.error(f"获取情感分析上下文历史失败: {e}")
            
        # 合并上下文 + 当前输入
        full_text = f"{context_text} {text}".strip()
        
        service = get_emotion_service()
        
        # 获取 CommonSettings 用于 LLM 配置 (如果需要翻译)
        # 优化：优先从 State 获取，如果不存在则查询并存入 State
        common = state.get("common_settings")
        if not common:
            logger.info("Emotion: Preloading CommonSettings from DB")
            common = await get_common_settings_async(state["user_id"])
            if common:
                state["common_settings"] = common
        else:
            logger.info("Emotion: Using cached CommonSettings")
        
        # 预加载 Active Profiles 并存入 State (供后续 Task 2/3 使用)
        if "active_profiles" not in state:
            logger.info("Emotion: Preloading Active Profiles from DB")
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            # 导入辅助函数 (为了避免循环导入，这里假设它在 generation.py 中，我们临时移动或重新实现)
            # 更好的做法是将 DB 查询逻辑移到 tools.py 或 emotion.py 内部
            # 这里为了快速实现，我们调用一个新辅助函数
            try:
                from .tools import get_active_profiles_async
                profiles = await get_active_profiles_async(state["user_id"])
                state["active_profiles"] = profiles
            except Exception as e:
                logger.error(f"Failed to preload active profiles: {e}")
                state["active_profiles"] = []

        # 分析 (使用完整上下文) - 异步包装器
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        # service.analyze 可能会调用 LLM 进行翻译（同步）或模型（CPU 绑定）。
        # 使用带缓存的异步方法
        user_message_id = state.get("user_message_id")
        user_id = state["user_id"]
        scores = await service.analyze_async(full_text, user_settings=common, trigger_message_id=user_message_id, user_id=user_id, original_text=text,
                                             execution_id=state.get("execution_id"))
        
        # Ekman 映射 (用户需求)
        # 将复杂的 GoEmotions 映射到 6 种基本情感
        ekman_scores = service._map_to_ekman(scores)
        sorted_ekman = sorted(ekman_scores.items(), key=lambda x: x[1], reverse=True)
        top = sorted_ekman[:3]
        
        # 计算投入度分数 (Interest Index)
        # 注意：我们仍然使用原始的 GoEmotions 分数来进行细粒度的投入度度量
        
        # 1. 强度 (非中性程度)
        neutral_score = scores.get('neutral', 0.0)
        intensity = 1.0 - neutral_score
        
        # 2. 特定的高唤醒/认知情感
        # 好奇、困惑、惊讶 -> 认知投入
        # 兴奋、快乐、愤怒、恐惧、渴望、爱 -> 情感唤醒
        arousal_keys = ['curiosity', 'confusion', 'surprise', 'realization', 
                        'excitement', 'joy', 'anger', 'fear', 'desire', 'love']
        
        max_arousal = 0.0
        for key in arousal_keys:
            if key in scores:
                max_arousal = max(max_arousal, scores[key])
                
        # 3. 输入长度因子 (对数式封顶)
        # 简单的线性增长，50字符达到 1.0
        len_score = min(len(text) / ENGAGEMENT_LENGTH_THRESHOLD, 1.0)
        
        # 基础评分 (0-1.0) - 基于单条消息的情感强度
        # 权重: 强度 50%, 最大唤醒度 30%, 长度 20%
        intensity_score = (ENGAGEMENT_WEIGHT_INTENSITY * intensity) + (ENGAGEMENT_WEIGHT_AROUSAL * max_arousal) + (ENGAGEMENT_WEIGHT_LENGTH * len_score)
        
        # 4. Reflexion 投入度 (E_U) - 基于交互上下文
        # 尝试获取上一轮 AI 回复，计算交互质量
        reflexion_eu_score = 0.5 # 默认中值
        reflexion_metrics = {}
        
        try:
            # 获取最近的历史消息 (排除当前正在处理的 pending 消息)
            recent_msgs_for_context = await loop.run_in_executor(
                None, 
                lambda: history_service.get_recent_history_limit(
                    state["user_id"], 
                    limit=5, 
                    db=None
                )
            )
            
            # 找到最近的一条 AI 消息
            last_ai_msg = None
            for msg in reversed(recent_msgs_for_context):
                if msg.role == "ai" and msg.status == "completed":
                    last_ai_msg = msg
                    break
            
            if last_ai_msg:
                # 计算响应时间 (当前时间 - 上一条AI消息时间)
                # 注意：request_start_ts 是本次请求开始时间
                req_ts = state.get("request_start_ts", time.time())
                # 库里存的是 naive UTC(见 core/time_utils.utc_now_naive)。
                # 直接 .timestamp() 会被按**本地时区**解释:在 UTC+8 下算出的
                # 响应时长恒定多出 8 小时,M_rtl(响应时间)这一项因此永远饱和,
                # 参与度评分里它等于常量 —— 喂给 Reflexion / RL 的信号是坏的。
                from ...core.time_utils import naive_utc_to_epoch
                ai_ts = naive_utc_to_epoch(last_ai_msg.timestamp)
                response_time = max(0.1, req_ts - ai_ts)
                
                # 计算 Reflexion E_U
                # prev_user_emotion 暂时无法轻易获取，传入空字典 (影响 M_sent)
                # 但 M_cont (话题延续性) 和 M_rtl (响应时间) 是有效的
                e_u_result = metrics_service.calculate_user_engagement(
                    agent_response=last_ai_msg.content,
                    user_next_input=text,
                    response_time_sec=response_time,
                    prev_user_emotion={}, 
                    next_user_emotion=ekman_scores
                )
                reflexion_eu_score = e_u_result["E_U"]
                reflexion_metrics = e_u_result
                logger.info(f"Reflexion E_U calculated: {reflexion_eu_score:.2f}", metrics=e_u_result)
            else:
                logger.info("No previous AI message found for Reflexion E_U calculation.")
                
        except Exception as e:
            logger.warning(f"Failed to calculate Reflexion E_U: {e}")

        # 综合评分 (0-100)
        # 融合 Intensity (当前情绪) 和 Reflexion E_U (交互质量)
        # 权重: Reflexion 60%, Intensity 40%
        final_score_normalized = 0.6 * reflexion_eu_score + 0.4 * intensity_score
        engagement_score = final_score_normalized * 100.0

        # 记录详细日志
        log_content = {
            "original_text": text,
            "context_merged_text": full_text,
            "text_length": len(text),
            "neutral_score": neutral_score,
            "intensity": intensity,
            "max_arousal": max_arousal,
            "intensity_score": intensity_score,
            "reflexion_eu_score": reflexion_eu_score,
            "reflexion_metrics": reflexion_metrics,
            "final_score": engagement_score
        }
        
        logger.info("情感与投入度分析 (Ekman + 上下文)", **log_content)

        # 把本轮情绪写进用户状态,供**主动关心**判断是否要走情感急救。
        #
        # 这个写入原先根本不存在:StateService.update_emotional_state 全库零调用者,
        # 于是 `user:{uid}:last_emotion` 永远是空,主动关心里的
        # 「Track A 情感急救」判定 `if emotional_state:` 永远为假 ——
        # 双轨门控实际上一直是单轨,负面情绪下最该主动关心的场景反而从不触发。
        try:
            if top:
                from ...services.proactive.state import StateService
                await StateService.update_emotional_state(state["user_id"], {
                    "label": top[0][0],
                    "score": float(top[0][1]),
                    "summary": text[:120],
                })
        except Exception as e:
            # 情绪留痕失败不能影响本轮对话
            logger.warning(f"写入情感状态失败: {e}")

        # 更新 Trace
        trace = await add_trace(state, "analyze",
            input_data={
                "received_user_input": text,
                "merged_context_text": full_text
            },
            output_data={
                "top_emotions": top, 
                "engagement_score": engagement_score,
                "ekman_scores": ekman_scores
            }
        )

        return {
            "execution_id": state["execution_id"], # 确保传递
            "request_start_ts": state["request_start_ts"], # 确保传递:就地赋值不进通道,save 的 SLO 记录依赖此键
            # route 必须由入口节点显式写入:route_logic 是 conditional entry point,
            # 其就地赋值不进通道、返回值仅用于选分支。缺失会导致 tool_check 早退、
            # DEEP 角色卡/超时/专用模型全部失效(见 state.py 契约第 5 条)
            "route": "DEEP",
            "emotion_scores": scores, # 保留原始分数供 RL Agent 和前端图表使用 (27维)
            "ekman_scores": ekman_scores, # 新增：供前端一致性展示
            "top_emotions": top, # 返回 Ekman 主要情感供展示
            "engagement_score": engagement_score,
            "workflow_trace": trace,
            "common_settings": common, # 显式返回，以便 StateGraph 更新 State
            "active_profiles": state.get("active_profiles", []) # 显式返回，以便 StateGraph 更新 State
        }
    except Exception as e:
        logger.error(f"Error in analyze_emotion: {e}")
        raise NodeError("EmotionAnalysis", e)
