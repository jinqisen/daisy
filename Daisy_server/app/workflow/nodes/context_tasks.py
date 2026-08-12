"""
DEEP 路径的并行上下文任务节点(自 generation.py 拆出,行为不变)。

这些节点在 `analyze` 之后并行执行,各自只产出自己负责的状态键:
- summarize_topic  → topic_summary        (Task 4)
- ensure_portrait  → portrait             (Task 1)
- analyze_style    → style_analysis       (Task 2, 依赖 love_style_weights)

汇聚与最终生成见 generation.py;上下文文本装配见 context_assembly.py。
"""

import asyncio
import structlog
from typing import List, Dict

from ..capability import essential, enhancement
from .state import AgentState
from .tools import add_trace, get_common_settings_async, monitor_execution_time
from ...core.database import SessionLocal
from ...core.exceptions import NodeError
from ...core.smart_cache import cache_node
from ...models import UserDB, CommonSettingsDB, RoleProfileDB
from ...prompts import CommonSettings, RoleProfile, get_style_analysis_prompt
from ...services.dialogue.generation import (
    generate_character_portrait_async,
    generate_topic_summary,
    generate_style_analysis,
)

logger = structlog.get_logger()


def _get_active_profiles_sync(user_id_str: str) -> List[RoleProfile]:
    """Helper to fetch profiles synchronously from DB"""
    try:
        with SessionLocal() as db:
            user = db.query(UserDB).filter(UserDB.username == user_id_str).first()
            if user:
                profiles = db.query(RoleProfileDB).filter(RoleProfileDB.user_id == user.id).all()
                return [
                    RoleProfile(
                        name=p.name,
                        description=p.description,
                        style=p.style,
                        constraints=p.constraints,
                    ) for p in profiles
                ]
    except Exception as e:
        logger.error(f"Failed to fetch profiles: {e}")
    return []


def _calculate_active_personas(active_profiles_list: List[RoleProfile], love_style_data: dict) -> tuple[List[tuple[RoleProfile, float]], List[str], dict]:
    """Calculate active personas based on weights"""
    # 确定权重
    weights = love_style_data.get("weights", {})
    if not weights:
        weights = {p.name: 1.0 for p in active_profiles_list}

    sorted_weights = sorted(weights.items(), key=lambda x: x[1], reverse=True)

    active_profiles = []
    mix_names = []
    for name, weight in sorted_weights:
        if weight < 0.05: continue

        profile_db = next((p for p in active_profiles_list if p.name == name), None)

        if profile_db:
            if len(active_profiles) >= 3: break

            profile = RoleProfile(
                name=profile_db.name,
                description=profile_db.description,
                style=profile_db.style,
                constraints=profile_db.constraints,
            )
            active_profiles.append((profile, weight))
            mix_names.append(f"{name} {int(weight*100)}%")

    return active_profiles, mix_names, weights


@enhancement(fallback={"topic_summary": ""})
@monitor_execution_time
async def summarize_topic(state: AgentState) -> AgentState:
    """
    独立节点：话题总结 (Task 4)
    并行执行，生成话题和上下文摘要
    """
    try:
        user_id = state["user_id"]
        user_input = state["user_input"]

        # 优化：从 State 获取 Common Settings
        common = state.get("common_settings")
        if common:
            logger.info(f"Task 4: Using cached common_settings from state (Type: {type(common)})")
        if not common:
            logger.warning("Task 4: Common settings not in state, fetching from DB")
            common = await get_common_settings_async(user_id)
            if common: state["common_settings"] = common
        if not common:
            raise ValueError(f"Failed to load common settings for user {user_id}")

        logger.info("Task 4: 开始话题总结")
        user_message_id = state.get("user_message_id")
        summary = await generate_topic_summary(user_id, common, user_input, trigger_message_id=user_message_id,
                                               execution_id=state.get("execution_id"))

        # 更新 Trace
        trace = await add_trace(state, "summarize_topic",
            input_data={
                "user_input": user_input
            },
            output_data={
                "topic_summary": summary
            }
        )

        return {"topic_summary": summary, "workflow_trace": trace}
    except Exception as e:
        logger.error(f"Error in summarize_topic: {e}")
        raise NodeError("TopicSummary", e)


@enhancement(fallback={"portrait": ""})
@cache_node(key_prefix="portrait", ttl=3600)
@monitor_execution_time
async def ensure_portrait(state: AgentState) -> AgentState:
    """
    独立节点：确保角色画像 (Task 1)
    如果 DB 中存在画像则使用，否则生成并保存
    """
    try:
        user_id = state["user_id"]

        # 优化：从 State 获取 Common Settings
        common = state.get("common_settings")
        if common:
            logger.info(f"Task 1: Using cached common_settings from state (Type: {type(common)})")
        if not common:
            logger.warning("Task 1: Common settings not in state, fetching from DB")
            common = await get_common_settings_async(user_id)
            if common: state["common_settings"] = common

        if not common:
            raise ValueError(f"Failed to load common settings for user {user_id}")

        portrait_text = common.portrait if common else ""

        # 如果没有画像，生成它
        if not portrait_text:
            logger.info("Task 1: Generating new portrait...")
            portrait_text = await generate_character_portrait_async(user_id, common, execution_id=state.get("execution_id"))

            # 保存回 DB
            def _save_portrait_sync(uid, p_text):
                try:
                    with SessionLocal() as db:
                        user = db.query(UserDB).filter(UserDB.username == uid).first()
                        if user:
                            common_db = db.query(CommonSettingsDB).filter(CommonSettingsDB.user_id == user.id).first()
                            if common_db:
                                common_db.portrait = p_text
                                db.commit()
                                logger.info("Task 1: Portrait saved to DB")
                except Exception as e:
                    logger.error(f"Failed to save portrait to DB: {e}")

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _save_portrait_sync, user_id, portrait_text)
        else:
            logger.info("Task 1: Using existing portrait from DB")

        # 更新 Trace
        trace = await add_trace(state, "ensure_portrait",
            input_data={"user_id": user_id},
            output_data={"portrait": portrait_text}
        )

        return {"portrait": portrait_text, "workflow_trace": trace}
    except Exception as e:
        logger.error(f"Error in ensure_portrait: {e}")
        raise NodeError("Portrait", e)


@enhancement(fallback={})
@cache_node(key_prefix="style_analysis", ttl=1800)
@monitor_execution_time
async def analyze_style(state: AgentState) -> AgentState:
    """
    独立节点：风格分析 (Task 2)
    依赖：analyze_communication_style (love_style_weights)
    """
    try:
        if "love_style_weights" not in state:
            # 依赖缺失时只跳过自身、不写 _skip_generation:该键是 generate/fast/standard
            # 的单写者键(见 state.py 契约)。
            # 双写会触发 LangGraph InvalidUpdateError;跳过语义由 generate 的汇聚检查兜底
            # (缺 style_analysis 即跳过)。
            logger.info("Analyze Style: Waiting for love_style_weights. Skipping.")
            return {}

        user_id = state["user_id"]
        user_input = state["user_input"]
        user_message_id = state.get("user_message_id")
        love_style_data = state["love_style_weights"]

        # 优化：从 State 获取 Common Settings
        common = state.get("common_settings")
        if not common:
            common = await get_common_settings_async(user_id)
            if common: state["common_settings"] = common

        if not common: common = CommonSettings(name="AI")

        # 优化：从 State 获取 Active Profiles
        active_profiles_list = state.get("active_profiles")
        if active_profiles_list:
            logger.info(f"Task 2: Using cached active_profiles from state (Count: {len(active_profiles_list)})")
        if not active_profiles_list:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            active_profiles_list = await loop.run_in_executor(None, _get_active_profiles_sync, user_id)
            if active_profiles_list: state["active_profiles"] = active_profiles_list

        active_profiles, mix_names, weights = _calculate_active_personas(active_profiles_list, love_style_data)

        # 生成 Prompt 仅用于日志记录
        debug_prompt = get_style_analysis_prompt(common, mix_names)
        logger.info("Task 2: 开始风格分析", prompt_preview=debug_prompt[:100] + "...")

        style_analysis = await generate_style_analysis(
            user_id,
            common,
            mix_names,
            user_input=user_input,
            trigger_message_id=user_message_id,
            active_profiles=active_profiles, # 传递完整的 Profile 对象以启用规则引擎优化
            execution_id=state.get("execution_id"),
        )

        trace = await add_trace(state, "analyze_style", input_data={"mix_names": mix_names, "prompt": debug_prompt}, output_data={"style_analysis": style_analysis})

        return {"style_analysis": style_analysis, "workflow_trace": trace}
    except Exception as e:
        logger.error(f"Error in analyze_style: {e}")
        raise NodeError("StyleAnalysis", e)
