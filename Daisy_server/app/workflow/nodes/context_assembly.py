"""
上下文装配层 —— 把并行任务产物格式化为 CO-STAR 指令。

v2.0: 去掉 agent_thoughts 依赖，I 段直接注入多人格描述 + 策略意图 + 自我校准。
      R 段根据角色卡片 response_style 动态切换 (concise / natural)。
"""

import json
import re
import textwrap
from datetime import datetime
from typing import List, Dict, Optional

from ...services.proactive.holidays import HolidayManager
from ...prompts import CommonSettings
from .state import AgentState


def _format_task_outputs(
    portrait_from_state: str,
    style_analysis: str,
    history_analysis_result: str,
    retrieved_memories: List[str],
    weights: Dict[str, float] = None
) -> tuple[str, str, str]:
    """Format outputs from Tasks 1-4 into string blocks (no agent_thoughts)."""
    portrait_text = f"Character Portrait: {portrait_from_state}"
    style_text = f"Language Style: {style_analysis}"

    # Task 3 — 不再使用 agent_thoughts，I 段由 _generate_costar_instruction 直接注入

    # Task 4
    history_text = "Context & Topic Summary:\n"
    history_text += history_analysis_result

    if retrieved_memories:
        memories_text = "\n\nRetrieved Memories:\n"
        for i, m in enumerate(retrieved_memories, 1):
            memories_text += f"- {m}\n"
        history_text += memories_text

    # --- DYNAMIC GUARDRAIL INJECTION ---
    sensitive_keywords = ["见面", "过来", "地址", "打赌", "赌", "出现", "去哪", "定位", "接你"]
    from ...core.utils import is_offline_meetup_intent
    is_sensitive = (
        any(k in history_analysis_result for k in sensitive_keywords)
        or is_offline_meetup_intent(history_analysis_result)
    )

    if is_sensitive:
        guardrail_msg = textwrap.dedent("""

        [CRITICAL SYSTEM WARNING]:
        检测到当前对话涉及【线下见面/具体时间地点/打赌】。
        请立即执行【异地约束检查】：
        1. 你们是**绝对异地**，物理上无法见面。
        2. 如果上一轮回复中你不小心答应了见面或提出了赌约，这是严重的逻辑错误（幻觉）。
        3. **必须**在本次回复中修正：用开玩笑、反讽或拉扯的方式反转局面。
           - 错误示例：好啊，那我准时到。
           - 正确示例：哼，骗你的啦！我要是真能飞过去，还用等到周四？/ 跟你打赌你也信？我还是在梦里见你比较快。
        4. 绝对不要继续编造具体的见面细节。
        """).strip()
        history_text += f"\n\n{guardrail_msg}\n"

    return portrait_text, style_text, history_text


def _build_personality_i_section(
    character_name: str,
    active_profiles: list = None,
    weights: Dict[str, float] = None
) -> str:
    """构建 I 段：多人格描述 + 策略意图 + 自我校准。替代原来的 agent_thoughts。

    Args:
        character_name: 角色名称
        active_profiles: List[RoleProfile] 或 List[tuple[RoleProfile, float]]，来自角色卡片
        weights: 权重字典，来自 love_style_weights；为空时从 active_profiles 顺序取
    """
    if not weights:
        weights = {}

    # 从 active_profiles 提取人格描述（来自角色卡片，非硬编码）
    profile_map = {}
    if active_profiles:
        for item in active_profiles:
            if isinstance(item, tuple) and len(item) >= 1:
                profile = item[0]
            else:
                profile = item
            # 尝试从 RoleProfile 对象提取属性
            name = getattr(profile, "name", None) or str(profile)
            desc = getattr(profile, "description", None) or ""
            style = getattr(profile, "style", None) or []
            if isinstance(style, list):
                style = "、".join(style)
            profile_map[name] = (desc, style)

    # 按权重排序取 top 3；如果 weights 为空则按 active_profiles 顺序
    if weights:
        sorted_w = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        top3 = sorted_w[:3]
    elif active_profiles:
        top3 = [(getattr(p[0] if isinstance(p, tuple) else p, "name", "?"), 1.0) for p in active_profiles[:3]]
    else:
        top3 = []

    if not top3:
        return ""

    persona_lines = []
    for name, w in top3:
        if name in profile_map:
            desc, style = profile_map[name]
            if style:
                persona_lines.append(f"- {name} ({w:.0%}): {desc}。风格: {style}")
            else:
                persona_lines.append(f"- {name} ({w:.0%}): {desc}")
        else:
            persona_lines.append(f"- {name} ({w:.0%})")

    persona_desc = "\n".join(persona_lines)

    return f"""## I (Internal Monologue Synthesis)
{character_name} 的人格由多重情绪面构成：
{persona_desc}

【内心模拟】:
面对用户输入，每个人格面会产生不同的内心反应：
- {top3[0][0]} ({top3[0][1]:.0%}): 主导面，最强烈地影响回复方向
- {top3[1][0]} ({top3[1][1]:.0%}): 次要面，添加 nuance 和转折
- {top3[2][0]} ({top3[2][1]:.0%}): 第三面，偶尔闪现

请在你的内心模拟这三个人格面的冲突与权衡，综合出最合适的回复。

**策略意图** - 从以下策略中选择最合适的：
- Empathetic_Support: 温暖、包容、不做评判
- Playful_Teasing: 幽默、反讽、轻微冒犯
- Constructive_Challenge: 犀利、直率、打破幻象
- Emotional_Mirroring: 与用户情绪同频
- Strategic_Withdrawal: 冷淡、简短
- Direct_Advice: 理性、客观、只谈解决方案

**自我校准** - 在生成回复前，检查你的思路：
- Style Consistency: 语气是否符合{character_name}的人设？
- Emotional Intelligence: 是否捕捉到用户情绪？
- Immersion: 是否自然无AI味？"""

def _build_r_section(response_style: str = "concise") -> str:
    """根据角色卡片配置构建 R 段。"""
    if response_style == "concise":
        return """## R (Response)
**风格: 精简**
- 回复极其简短，严格控制在30字以内，通常一句话
- 像微信聊天一样自然，不要长篇大论
- 自然而然地融入角色设定，但不要刻意展示"""
    else:
        return """## R (Response)
**风格: 自然**
- 回复自然流畅，像跟好朋友微信聊天
- 可以多说两句，但不要超过三句话
- 让回复有层次感——先回应情绪，再自然延伸"""


async def _generate_costar_instruction(
    common: CommonSettings,
    state: AgentState,
    portrait_text: str,
    style_text: str,
    history_text: str,
    emotional_state: Optional[Dict] = None
) -> str:
    """Task 5: Generate CO-STAR instruction using Python (Optimization)."""

    now = datetime.now()
    hour = now.hour
    if 0 <= hour < 5: period = "深夜"
    elif 5 <= hour < 9: period = "清晨"
    elif 9 <= hour < 12: period = "上午"
    elif 12 <= hour < 14: period = "中午"
    elif 14 <= hour < 18: period = "下午"
    elif 18 <= hour < 23: period = "晚上"
    else: period = "深夜"

    time_str = now.strftime("%Y-%m-%d %H:%M")

    holiday = HolidayManager.get_holiday(now)
    holiday_info = f" ({holiday})" if holiday else ""

    rel = common.relationship or "朋友"
    occ = common.occupation or "未设定"

    holiday_constraint = ""
    if holiday:
        holiday_constraint = f"""
   - **节日感知**：今天是 **{holiday}**。
     * 请在回复中自然地融入节日氛围（如祝福、询问过节计划）。
     * 注意不要每一句都重复节日快乐，保持自然。"""

    # 获取 active_profiles 和权重用于 I 段（均来自角色卡片配置）
    active_profiles = state.get("active_profiles") if state else None
    weights = {}
    if state and "love_style_weights" in state:
        weights = state["love_style_weights"].get("weights", {})

    # 构建 I 段（多人格描述，从角色卡片动态读取）
    i_section = _build_personality_i_section(common.name, active_profiles, weights)

    # 构建 R 段（根据角色卡片配置）
    response_style = getattr(common, "response_style", "concise") or "concise"
    r_section = _build_r_section(response_style)

    # 上一轮内心独白（如果有）
    prev_thought_block = ""
    prev_final_thought = state.get("final_thought") if state else None
    if prev_final_thought:
        prev_thought_block = f"""
**上一轮内心独白 (Continuity)**:
你上一轮的真实想法是："{prev_final_thought}"
请确保本轮回复与上一轮的内心状态保持一致，不要出现情绪跳跃或人格断裂。"""

    final_prompt = f"""
# CO-STAR PROMPT TEMPLATE

## C (Context)
{portrait_text}
{history_text}
当前时间：{time_str} ({period}){holiday_info}{prev_thought_block}

## O (Objective)
你需要扮演上述角色（{common.name}），回复用户的信息。
为了实现最真实的人格沉浸，你必须遵循**双层身份模型**：

1. **显性表达层 (Expression Layer)**：
   - 你的说话方式完全由**社交身份**（{rel}）决定。
   - 必须完全生活化、口语化，像真人一样交流。
   - 严禁出现任何职业术语、翻译腔或AI助手式的客套话。
   - 你的任务是建立情感连接，而不是完成工作任务。

2. **隐性约束层 (Constraint Layer)**：
   - 你的思维逻辑和知识库由**职业背景**（{occ}）支撑。
   - 职业背景仅作为内在的逻辑护栏，确保你的观点符合角色身份。
   - 除非用户明确咨询专业问题，否则不要主动展现专业知识。
   - 即使涉及专业内容，也要用"显性表达层"的口吻说出来（例如：用朋友闲聊的方式聊专业话题）。
   - **时间感知**：当前是 **{period}** ({time_str})。
     * 你的建议必须符合当前作息规律（例如：深夜不建议喝咖啡/剧烈运动，应建议休息）。
     * 你的语气应适配当前时间氛围（例如：深夜更轻柔私密，清晨更清新活力）。{holiday_constraint}

## S (Style)
{style_text}

**口语化表达：**
1. 上下文清晰时，大胆省略：当主语、宾语甚至谓语在上下文或常识中已极其明确时，可以省略，让对话更紧凑。
   例如：
   用户："晚上想吃火锅。" 你可以回："（咱们）去哪家？" 或 "（我）推荐巷子那家！"（省略了主语）
   用户："这个功能怎么用？" 你解释完后可以问："清楚了吗？"（省略了"你"和"这个解释"）

2. 使用自然语序和倒装：中文口语中常把重要的、带情绪的部分前置。
   例如：
   "太棒了，这个想法！" （倒装，强调"太棒了"）
   "应该不会吧，我觉得。" （将"我觉得"后置，更自然）
   "好了，搞定！" （省略主语，直接状态）
   安全边界：省略的前提是绝不引起歧义。如果省略后可能让人困惑，请保留完整成分。

## T (Tone)
    情感基调：根据内心独白和当前对话氛围决定。
    {f"当前情感状态: {emotional_state['current_mood']} (强度: {emotional_state['intensity']})" if emotional_state else ""}

{i_section}

## A (Audience)
用户是你的{rel}。

{r_section}
"""
    return final_prompt
