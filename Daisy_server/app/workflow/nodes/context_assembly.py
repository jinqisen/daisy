"""
上下文装配层(自 generation.py 拆出,行为不变)。

职责:把并行任务的产物(画像/风格/内心独白/话题摘要/记忆)格式化为文本块,
并构建最终的 CO-STAR 指令。纯函数,无状态副作用,便于单测。

注意:_format_task_outputs 内含「敏感话题动态护栏」注入逻辑——按 §5 深改点
「跨 route 上下文构造统一」,该护栏后续应收编进统一护栏层。
"""

import json
import textwrap
from datetime import datetime
from typing import List, Dict, Optional

from ...services.proactive.holidays import HolidayManager
from ...prompts import CommonSettings
from .state import AgentState


def _format_task_outputs(portrait_from_state: str, style_analysis: str, agent_thoughts: dict, history_analysis_result: str, retrieved_memories: List[str], weights: Dict[str, float] = None) -> tuple[str, str, str, str]:
    """Format outputs from Tasks 1-4 into string blocks"""
    # Task 1
    portrait_text = f"Character Portrait: {portrait_from_state}"

    # Task 2
    style_text = f"Language Style: {style_analysis}"

    # Task 3
    os_text = ""
    if agent_thoughts:
        # 简化输出格式，移除冗余层级
        thoughts_str = ""
        for name, content in agent_thoughts.items():
            # 尝试解析 content 为 dict (如果它是 JSON 字符串)
            try:
                if isinstance(content, str) and content.strip().startswith('{'):
                    content_dict = json.loads(content)
                    strategy = content_dict.get("strategy", "None")
                    thought = content_dict.get("thought", content)
                else:
                    strategy = "General"
                    thought = content
            except:
                strategy = "General"
                thought = content

            weight = weights.get(name, 0)
            weight_str = f" ({weight:.0%})" if weight > 0 else ""

            if isinstance(thought, dict):
                # Handle structured dict from new engine
                strategy = thought.get("strategy", "None")
                content = thought.get("content", "")
                thoughts_str += f"- {name}{weight_str} [Strategy: {strategy}]: {content}\n"
            else:
                # Fallback for legacy/unstructured output
                thoughts_str += f"- {name}{weight_str}: {thought}\n"

        os_text += f"Inner Thoughts:\n{thoughts_str}"
    else:
        os_text += "Inner Thoughts: None"

    # Task 4
    history_text = "Context & Topic Summary:\n"
    # Remove verbose schema definitions to save tokens and focus attention
    # history_text += "**Analysis Schema (Reference)**:\n..."

    history_text += history_analysis_result

    # Append Retrieved Memories to Task 4 (or as a separate section)
    if retrieved_memories:
        memories_text = "\n\nRetrieved Memories:\n"
        for i, m in enumerate(retrieved_memories, 1):
            memories_text += f"- {m}\n"
        history_text += memories_text

    # --- DYNAMIC GUARDRAIL INJECTION ---
    # 动态检测敏感话题并注入强制约束
    # 关键词：见面、过来、江滩、地址、时间、打赌、周四
    # 注意:此表原先含「江滩」「老渡口」「周四」等具体地名/日期 —— 那是从某次具体对话
    # 抄来的,过拟合到单个历史案例,换个用户或场景就完全失效。改为通用语义词 +
    # 复用统一的线下见面判定(utils.is_offline_meetup_intent),避免各处各自维护关键词表。
    sensitive_keywords = ["见面", "过来", "地址", "打赌", "赌", "出现", "去哪", "定位", "接你"]
    # 检查是否最近的 summary 或者 user input 触发了敏感词
    # 注意：history_analysis_result 包含了最近的对话摘要

    # 简单检测：只要 Summary 中包含这些词，就说明最近在讨论这些
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

    return portrait_text, style_text, os_text, history_text


async def _generate_costar_instruction(common: CommonSettings, state: AgentState, portrait_text: str, style_text: str, os_text: str, history_text: str, emotional_state: Optional[Dict] = None) -> str:
    """Task 5: Generate CO-STAR instruction using Python (Optimization)"""
    # 直接构建 Prompt，不再调用 LLM

    # 获取当前时间
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

    # 获取节日信息
    holiday = HolidayManager.get_holiday(now)
    holiday_info = f" ({holiday})" if holiday else ""

    # 准备变量以防 None
    rel = common.relationship or "朋友"
    occ = common.occupation or "未设定"

    # 构建 Prompt
    holiday_constraint = ""
    if holiday:
        holiday_constraint = f"""
   - **节日感知**：今天是 **{holiday}**。
     * 请在回复中自然地融入节日氛围（如祝福、询问过节计划）。
     * 注意不要每一句都重复节日快乐，保持自然。"""

    final_prompt = f"""
# CO-STAR PROMPT TEMPLATE

## C (Context)
{portrait_text}
{history_text}
当前时间：{time_str} ({period}){holiday_info}

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
   - 即使涉及专业内容，也要用“显性表达层”的口吻说出来（例如：用朋友闲聊的方式聊专业话题）。
   - **时间感知**：当前是 **{period}** ({time_str})。
     * 你的建议必须符合当前作息规律（例如：深夜不建议喝咖啡/剧烈运动，应建议休息）。
     * 你的语气应适配当前时间氛围（例如：深夜更轻柔私密，清晨更清新活力）。{holiday_constraint}

## S (Style)
{style_text}

**口语化表达：**
1. 上下文清晰时，大胆省略：当主语、宾语甚至谓语在上下文或常识中已极其明确时，可以省略，让对话更紧凑。
   例如：
   用户：“晚上想吃火锅。” 你可以回：“（咱们）去哪家？” 或 “（我）推荐巷子那家！”（省略了主语）
   用户：“这个功能怎么用？” 你解释完后可以问：“清楚了吗？”（省略了“你”和“这个解释”）

2. 使用自然语序和倒装：中文口语中常把重要的、带情绪的部分前置。
   例如：
   “太棒了，这个想法！” （倒装，强调“太棒了”）
   “应该不会吧，我觉得。” （将“我觉得”后置，更自然）
   “好了，搞定！” （省略主语，直接状态）
   安全边界：省略的前提是绝不引起歧义。如果省略后可能让人困惑，请保留完整成分。

## T (Tone)
    情感基调：根据内心独白和当前对话氛围决定。
    {f"当前情感状态: {emotional_state['current_mood']} (强度: {emotional_state['intensity']})" if emotional_state else ""}

    ## I (Internal Monologue Synthesis)
{os_text}

**Step 1: Thought Synthesis**
Review the "Conflicting Inner Voices" above.
Based on the "Influence" percentage of each facet, synthesize a single, complex "Final Inner Thought".
- The dominant facet (higher influence) should drive the main intent.
- The minor facet (lower influence) should add nuance, hesitation, or specific emotional coloring.
- You MUST output the synthesized thought first in the format: `[Final Inner Thought]: ...`

**策略意图 (Strategic Intent):**
如果【内心独白】中明确了 [Strategy]，请严格执行该策略：
- Empathetic_Support: 温暖、包容、不做评判。
- Playful_Teasing: 幽默、反讽、轻微冒犯。
- Constructive_Challenge: 犀利、直率、打破幻象。
- Emotional_Mirroring: 与用户情绪同频。
- Strategic_Withdrawal: 冷淡、简短。
- Direct_Advice: 理性、客观、只谈解决方案。

## A (Audience)
用户是你的{rel}。

## R (Response)
回复要求：
1. **Output Structure**:
   [Final Inner Thought]: (Your synthesized thought here)

   (Your actual response to the user)

2. **Response Content**:
   - Do NOT include any prefix for the response part.
   - Do NOT output the thought again in the response.
3. **长度严格限制**：回复必须简短，通常不超过两句话。如果内容较多，请自行拆分为多次回复（但本次仅输出第一段，后续内容等待下次交互或自行省略）。
4. 避免长篇大论，保持聊天软件（如微信）的即时通讯风格。
"""
    return final_prompt
