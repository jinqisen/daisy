"""
跨路由共享的基础 system prompt 构造(深改点「跨 route 上下文构造统一」首增量)。

统一 FAST / STANDARD 此前各自复制的拼装逻辑:
    core system instructions → 用户模板 → 线下见面输入检查 → 角色卡 addendum

设计说明:
- is_offline_meetup_intent 检查是全代码库唯一的「输入校验→条件化约束注入」雏形,
  在此收编为统一输入校验层的种子;路由层(graph.route_logic)会把此类输入强制导向
  DEEP,因此该检查在 FAST/STANDARD 属防御性兜底(缓存/直连状态等旁路场景)。
- 角色卡加载失败一律降级为「无 addendum」并告警,不让人设增强失败阻断回复
  (对齐异常处理原则:fallback 优于失败)。
- DEEP 路径的动态护栏/patches 注入仍在 generation.py,后续增量再收编。
"""

import structlog

from ...core.utils import is_offline_meetup_intent
from ...prompts import get_core_system_instructions
from ...services.persona.character_card import (
    get_character_card,
    build_channel_prompt_addendum,
    infer_relationship_stage,
)

logger = structlog.get_logger()

OFFLINE_MEETUP_CONSTRAINT = "你们是绝对异地关系，不能答应任何线下见面或提出线下邀约，也不能编造具体时间地点。"
FALLBACK_SYSTEM_PROMPT = "收到信息像人一样回复交流。"


def build_base_system_prompt(common, user_id, channel: str, user_input: str) -> str:
    """
    构造某条路由(channel: "FAST" | "STANDARD")的基础 system prompt。

    common 为 None 时返回极简兜底提示,与旧实现一致。
    """
    system_prompt = get_core_system_instructions(common) if common else FALLBACK_SYSTEM_PROMPT

    if common and getattr(common, "system_prompt_template", None):
        system_prompt = f"{system_prompt}\n\n{common.system_prompt_template}".strip()

    # 统一输入校验层(种子):线下见面意图 → 注入硬约束
    if is_offline_meetup_intent(user_input):
        system_prompt = f"{system_prompt}\n\n{OFFLINE_MEETUP_CONSTRAINT}".strip()

    # 角色卡 addendum(失败降级,不阻断)
    card = None
    try:
        card = get_character_card(user_id)
    except Exception as e:
        logger.warning(f"{channel} path failed to load character card: {e}")

    if card:
        stage = infer_relationship_stage(getattr(common, "relationship", None) if common else None)
        addendum = build_channel_prompt_addendum(card, channel, user_input, stage)
        if addendum:
            system_prompt = f"{system_prompt}\n\n{addendum}".strip()

    return system_prompt
