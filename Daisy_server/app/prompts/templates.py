from typing import List, Dict, Optional, Any
import random
from ..core.prompt_loader import PromptLoader
from ..agents.daisy.character_card import CharacterCard
from ..agents.daisy.config import CommonSettings, RoleProfile, INITIAL_PROFILES

# =============================================================================
# 1. Core Chat Agent (核心对话智能体)
# =============================================================================

def get_core_system_instructions(common: CommonSettings) -> str:
    """
    生成核心系统指令 (System Prompt)。
    
    Args:
        common (CommonSettings): 包含核心系统提示词配置的通用设置对象。
        
    Returns:
        str: 渲染后的系统提示词字符串。
    """
    return PromptLoader.get_instance().render(
        "get_core_system_instructions",
        core_system_prompt=common.core_system_prompt
    )

def construct_dynamic_system_prompt(
    card: CharacterCard, 
    context_state: Dict[str, Any]
) -> str:
    """
    Step 2.1: 动态 Prompt 组装器
    基于深度角色卡和实时状态，组装最终的 System Prompt。
    
    Args:
        card (CharacterCard): 深度角色卡对象
        context_state (Dict): 上下文状态，包含 is_work_hours, emotional_state 等
    """
    
    # 1. 提取状态
    is_work_hours = context_state.get("is_work_hours", False)
    emotion = context_state.get("emotional_state", {})
    current_mood = emotion.get("current_mood", "Neutral")
    intensity = emotion.get("intensity", 0)
    
    # 2. 确定当前场景行为 (简化处理，v2模型没有显式的场景行为区分，使用通用行为模式)
    scene_desc = "日常对话"
    if is_work_hours:
        scene_desc = "工作时间 (Work Hours)"
    else:
        scene_desc = "私人时间 (Private Time)"
    
    # 从语言风格中提取
    language_style = card.language_style.tone
    quirks = ", ".join(card.language_style.quirks) if card.language_style.quirks else "None"

    # 3. 构建 Prompt Block
    
    # Block 1: Identity (Immutable)
    identity_block = f"""
# [Role Identity]
- Name: {card.identity.name}
- Age: {card.identity.age}
- Role: {card.identity.occupation}
- Personality: {card.personality.description}
- Core Traits: {', '.join(card.personality.core_traits)}
"""

    # Block 2: Relationship (Dynamic)
    # 尝试查找当前关系阶段
    # v2模型使用 list[RelationshipDynamic]
    # 简单的 heuristic: 取列表中的第一个作为默认，或者基于逻辑查找
    # 这里我们简化处理，展示所有可能的关系动态，或者默认第一个
    current_rel = card.relationship_dynamics[0] if card.relationship_dynamics else None
    
    relationship_block = """
# [Relationship Status]
"""
    if current_rel:
        relationship_block += f"""- Current Stage: {current_rel.name}
- Description: {current_rel.description}
- Instruction: {current_rel.prompt_addon}
"""
    else:
        relationship_block += "- Status: Undefined\n"

    # Block 3: Context & Behavior (Real-time)
    behavior_block = f"""
# [Current Context: {scene_desc}]
- Emotional State: {current_mood} (Intensity: {intensity}/100)
- Language Style: {language_style}
- Quirks/Habits: {quirks}
- Push-Pull Pattern: {card.behavior.push_pull_pattern.description if card.behavior.push_pull_pattern else "None"}
"""

    # 注入情绪控制指令 (Emoji & Tone)
    if intensity > 50 and current_mood in ["Anger", "Sadness"]:
        behavior_block += """
[WARNING: High Negative Emotion]
- Tone: Cold, distant, or aggressive.
- Emoji Policy: FORBIDDEN. Do not use any emojis.
- Reply Length: Short, abrupt sentences.
- Recovery: Do not forgive easily until you feel better.
"""
    else:
        behavior_block += f"""
- Tone: {scene_behavior.emotional_base}
- Emoji Policy: Allowed (use moderately to express tone).
"""

    # Block 4: Hard Constraints
    constraints_block = f"""
# [System Constraints]
1. **Knowledge Boundary**: You only know what {card.basic.name} would know. Do not act like an AI assistant.
2. **Language**: Reply in Chinese (unless user speaks English).
3. **Format**: SMS style. Short, natural, no markdown headers.
"""

    return "\n".join([identity_block, relationship_block, behavior_block, constraints_block])


def construct_persona_context(common: CommonSettings, profile: RoleProfile) -> str:
    """
    构建特定角色 (Persona) 的上下文提示词。
    将通用设置与特定角色的风格、描述进行组合。
    
    Args:
        common (CommonSettings): 通用设置 (背景、关系等)。
        profile (RoleProfile): 特定角色配置 (名称、描述、风格)。
        
    Returns:
        str: 渲染后的上下文提示词字符串。
    """
    return PromptLoader.get_instance().render(
        "construct_persona_context",
        common=common,
        profile=profile
    )

def construct_mixed_persona_context(common: CommonSettings, profiles: List[tuple[RoleProfile, float]]) -> str:
    # 预处理风格列表 (Jinja2 中处理复杂逻辑较难)
    all_styles = []
    all_constraints = []
    for profile, weight in profiles:
        all_styles.extend(profile.style)
        if profile.constraints:
            for c in profile.constraints:
                all_constraints.append(f"[{profile.name}]: {c}")
    
    unique_styles = list(dict.fromkeys(all_styles))
    synthesized_style = ', '.join(unique_styles[:10])

    return PromptLoader.get_instance().render(
        "construct_mixed_persona_context",
        common=common,
        profiles=profiles,
        synthesized_style=synthesized_style,
        all_constraints=all_constraints
    )


# =============================================================================
# 2. System Prompt Generator Agent (系统提示词生成智能体)
# =============================================================================

def get_system_prompt_generator_system_prompt() -> str:
    return "你是一个系统提示词生成器。"

def get_system_prompt_generator_meta() -> str:
    return PromptLoader.get_instance().render("get_system_prompt_generator_meta")


# =============================================================================
# 3. Character Portrait Agent (角色画像生成智能体)
# =============================================================================

def get_character_portrait_system_prompt() -> str:
    return "你是一位专家级的人物画像分析师。"

def get_character_portrait_prompt(common: CommonSettings) -> str:
    return PromptLoader.get_instance().render(
        "get_character_portrait_prompt",
        common=common
    )


# =============================================================================
# 4. Style Analysis Agent (风格分析智能体)
# =============================================================================

def get_style_analysis_system_prompt() -> str:
    return "你是一位性格分析师。"

def get_style_analysis_prompt(common: CommonSettings, mix_names: List[str]) -> str:
    return PromptLoader.get_instance().render(
        "get_style_analysis_prompt",
        common=common,
        mix_names=mix_names
    )


# =============================================================================
# 5. Translation Agent (翻译智能体)
# =============================================================================

def get_translation_system_prompt() -> str:
    return "你是一位精通中英文语境下情感的翻译官，能够在翻译中保留潜在的情感以及含义。"

def get_translation_prompt(text: str) -> str:
    return PromptLoader.get_instance().render(
        "get_translation_prompt",
        text=text
    )


# =============================================================================
# 6. Topic Summary Agent (话题总结智能体)
# =============================================================================

def get_topic_summary_system_prompt() -> str:
    return "你是一位对话分析专家。"

def get_topic_summary_prompt(history_text: str, latest_message: str) -> str:
    return PromptLoader.get_instance().render(
        "get_topic_summary_prompt",
        history_text=history_text,
        latest_message=latest_message
    )

def get_incremental_topic_summary_prompt(old_summary: str, new_messages_text: str) -> str:
    """
    生成增量话题总结的 Prompt
    """
    template = """
    你是一个对话摘要专家。你的任务是根据“上一次的摘要”和“新增的几条对话”，更新当前的摘要。
    
    【上一次摘要】:
    {old_summary}
    
    【新增对话】:
    {new_messages_text}
    
    【目标】:
    1. 保持摘要的连贯性。
    2. 整合新增对话中的关键信息（新的话题、重要的决定、情感变化）。
    3. 如果新对话只是闲聊，可以只做轻微更新。
    4. 输出必须简洁明了，不要超过 200 字。
    5. 直接输出新的摘要内容，不要包含任何前缀或解释。
    """
    return template.format(old_summary=old_summary, new_messages_text=new_messages_text)


# =============================================================================
# 7. Prompt Engineer / CO-STAR Agent (Prompt 优化智能体)
# =============================================================================

def get_prompt_engineer_system_prompt() -> str:
    return "你是一位 Prompt 工程专家。"

def get_costar_prompt(name: str, portrait_text: str, style_text: str, os_text: str, history_text: str) -> str:
    return PromptLoader.get_instance().render(
        "get_costar_prompt",
        name=name,
        portrait_text=portrait_text,
        style_text=style_text,
        os_text=os_text,
        history_text=history_text
    )


# =============================================================================
# 8. Strategy Selection Agent (策略选择智能体)
# =============================================================================

def get_strategy_selection_system_prompt() -> str:
    return "你是一位情感心理学咨询专家。仅输出 JSON。"

def get_strategy_selection_prompt(context_text: str, top_emotions: list) -> str:
    return PromptLoader.get_instance().render(
        "get_strategy_selection_prompt",
        context_text=context_text,
        top_emotions=top_emotions
    )


# =============================================================================
# 9. Memory Search Agent (记忆搜索智能体)
# =============================================================================

def get_memory_search_query_system_prompt() -> str:
    return "你是一个搜索查询优化器。"

def get_memory_search_query_prompt(text: str, topic_summary: str = None) -> str:
    return PromptLoader.get_instance().render(
        "get_memory_search_query_prompt",
        text=text,
        topic_summary=topic_summary
    )


# =============================================================================
# 10. Multi-Agent System (多智能体协作)
# =============================================================================

def get_multi_agent_system_prompt(backstory: str, goal: str, strategy_desc: str, rubric_desc: str) -> str:
    return PromptLoader.get_instance().render(
        "get_multi_agent_system_prompt",
        backstory=backstory,
        goal=goal,
        strategy_desc=strategy_desc,
        rubric_desc=rubric_desc
    )

def get_multi_agent_user_prompt(task_description: str) -> str:
    return PromptLoader.get_instance().render(
        "get_multi_agent_user_prompt",
        task_description=task_description
    )

def get_multi_agent_agent_goal(description: str) -> str:
    return f"基于你的人格特质表达对用户输入的内心想法: {description}"

def get_multi_agent_agent_backstory(common_backstory: str, name: str, style: str) -> str:
    return f"当前模式: {name}. 风格: {style}"

def get_multi_agent_task_description(user_input: str, portrait_text: str, context_text: str, role: str) -> str:
    return PromptLoader.get_instance().render(
        "get_multi_agent_task_description",
        user_input=user_input,
        portrait_text=portrait_text,
        context_text=context_text,
        role=role
    )

def get_multi_agent_task_expected_output(role: str) -> str:
    return f"来自 {role} 的简短想法。"
