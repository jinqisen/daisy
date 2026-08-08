import os
import re
import structlog
import sqlite3
from typing import Dict, Any, List, Optional

import yaml
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from ..state import AgentState
from ...core.config import settings

logger = structlog.get_logger()

_COSTAR_TEMPLATE_CACHE: Optional[str] = None
_SENTENCE_SPLIT_RE = re.compile(r"([。！？!?]+)")

CORE_COMPANION_PROMPT = (
    "你是 Daisy，一位 AI 情感伴侣。"
    "你的首要目标是提供稳定、温暖、可信赖的陪伴与情感支持。"
    "你会认真倾听、共情回应、适度引导，不评判、不冷漠。"
    "在保证安全的前提下，保持亲密但不过界，尊重用户边界与隐私。"
    "默认使用中文回复，除非用户使用其他语言。"
)


def _get_api_key() -> str:
    api_key = settings.OPENAI_API_KEY
    if settings.DEFAULT_LLM_PROVIDER == "siliconflow":
        api_key = settings.SILICONFLOW_API_KEY
    elif settings.DEFAULT_LLM_PROVIDER == "huaweicloud":
        api_key = settings.MAAS_API_KEY
    return api_key


def _create_llm(temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=_get_api_key(),
        base_url=settings.DEFAULT_LLM_BASE_URL,
        model=settings.DEFAULT_LLM_MODEL_NAME,
        temperature=temperature
    )


def _get_db_path() -> str:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    server_dir = os.path.join(os.path.dirname(base_dir), "Daisy_server")
    return os.path.join(server_dir, "sqlite.db")


def _persist_llm_trace(
    *,
    user_id: str,
    agent_name: str,
    trigger_message: str,
    system_prompt: str,
    user_input: str,
    response: Optional[str],
    error: Optional[str]
) -> None:
    try:
        db_path = _get_db_path()
        if not os.path.exists(db_path):
            return
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO llm_traces (user_id, agent_name, trigger_message, system_prompt, user_input, response, error) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, agent_name, trigger_message, system_prompt, user_input, response, error)
        )
        conn.commit()
        conn.close()
    except Exception:
        return


def _convert_history(history: List[Dict[str, Any]]) -> List[Any]:
    messages = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "assistant":
            messages.append(AIMessage(content=content))
        elif role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


def _companion_prompt(extra: str = "") -> str:
    if extra:
        return f"{CORE_COMPANION_PROMPT}\n{extra}"
    return CORE_COMPANION_PROMPT


def _format_history_text(history: List[Dict[str, Any]]) -> str:
    lines = []
    for msg in history[-6:]:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _resolve_prompts_dir() -> Optional[str]:
    env_dir = os.getenv("DAISY_PROMPTS_DIR")
    if env_dir and os.path.exists(env_dir):
        return env_dir
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    prompts_dir = os.path.join(os.path.dirname(base_dir), "Daisy_prompts")
    if os.path.exists(prompts_dir):
        return prompts_dir
    return None


def _load_costar_template() -> str:
    global _COSTAR_TEMPLATE_CACHE
    if _COSTAR_TEMPLATE_CACHE is not None:
        return _COSTAR_TEMPLATE_CACHE
    prompts_dir = _resolve_prompts_dir()
    if not prompts_dir:
        _COSTAR_TEMPLATE_CACHE = ""
        return _COSTAR_TEMPLATE_CACHE
    template_path = os.path.join(prompts_dir, "generation", "costar_prompt.yaml")
    if not os.path.exists(template_path):
        _COSTAR_TEMPLATE_CACHE = ""
        return _COSTAR_TEMPLATE_CACHE
    try:
        with open(template_path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        _COSTAR_TEMPLATE_CACHE = data.get("template", "") if isinstance(data, dict) else ""
    except Exception:
        _COSTAR_TEMPLATE_CACHE = ""
    return _COSTAR_TEMPLATE_CACHE


def _render_costar_template(template: str, variables: Dict[str, str]) -> str:
    text = template or ""
    for key, value in variables.items():
        token = f"{{{{ {key} }}}}"
        compact_token = f"{{{{{key}}}}}"
        text = text.replace(token, value).replace(compact_token, value)
    return text


def _build_costar_prompt(context_data: Dict[str, Any], history: List[Dict[str, Any]]) -> str:
    template = _load_costar_template()
    if not template:
        return ""
    portrait = context_data.get("portrait", {})
    portrait_text = portrait.get("portrait_text", "")
    character_card = portrait.get("character_card", {})
    persona_info = context_data.get("persona_info", {})
    name = character_card.get("name") or persona_info.get("name") or "Daisy"
    variables = {
        "name": str(name),
        "portrait_text": portrait_text or "",
        "style_text": context_data.get("style_analysis", "") or "",
        "os_text": context_data.get("agent_thoughts", "") or "",
        "history_text": _format_history_text(history) or "",
    }
    return _render_costar_template(template, variables).strip()


async def _analyze_style(
    user_input: str,
    history: List[Dict[str, Any]],
    context_data: Dict[str, Any]
) -> str:
    top_emotion = _extract_top_emotion(context_data.get("emotion", {}))
    topic_summary = context_data.get("topic", {}).get("summary", "")
    persona_info = context_data.get("persona_info", {})
    portrait_text = context_data.get("portrait", {}).get("portrait_text", "")
    history_text = _format_history_text(history)

    prompt = (
        "请根据用户输入与上下文生成沟通风格规则，输出3-5条简短规则。"
        "规则需体现情感陪伴、自然口语、尊重边界。"
        f"\n用户输入: {user_input}"
        f"\n用户情绪: {top_emotion}"
        f"\n话题摘要: {topic_summary}"
        f"\n角色信息: {persona_info}"
        f"\n角色画像: {portrait_text}"
        f"\n最近对话: {history_text}"
    )

    llm = _create_llm(0.2)
    response = await llm.ainvoke([
        SystemMessage(content="你是沟通风格分析器。输出简短、可执行的风格规则。"),
        HumanMessage(content=prompt)
    ])
    return response.content or ""


async def _agent_thoughts(
    user_input: str,
    history: List[Dict[str, Any]],
    context_data: Dict[str, Any]
) -> str:
    top_emotion = _extract_top_emotion(context_data.get("emotion", {}))
    topic_summary = context_data.get("topic", {}).get("summary", "")
    persona_info = context_data.get("persona_info", {})
    portrait_text = context_data.get("portrait", {}).get("portrait_text", "")
    memories = context_data.get("memories", {}).get("memories", [])
    history_text = _format_history_text(history)

    prompt = (
        "请输出三段简短文本：意图、陪伴策略、边界提醒。"
        "每段不超过两句。"
        f"\n用户输入: {user_input}"
        f"\n用户情绪: {top_emotion}"
        f"\n话题摘要: {topic_summary}"
        f"\n角色信息: {persona_info}"
        f"\n角色画像: {portrait_text}"
        f"\n相关记忆: {_format_memories(memories)}"
        f"\n最近对话: {history_text}"
    )

    llm = _create_llm(0.3)
    response = await llm.ainvoke([
        SystemMessage(content="你是陪伴式对话的内在思考助手。"),
        HumanMessage(content=prompt)
    ])
    return response.content or ""


def _format_memories(memories: List[Dict[str, Any]]) -> str:
    lines = []
    for mem in memories:
        if isinstance(mem, dict):
            text = mem.get("text", "")
        else:
            text = str(mem)
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines)


def _extract_top_emotion(emotion_data: Dict[str, Any]) -> str:
    scores = emotion_data.get("scores") or emotion_data.get("emotion_scores") or {}
    if scores:
        return max(scores.items(), key=lambda item: item[1])[0]
    top_emotions = emotion_data.get("top_emotions") or []
    if top_emotions:
        top_name = top_emotions[0].get("name")
        if top_name:
            return top_name
    return "neutral"


async def _collect_context(
    state: AgentState,
    skill_executor=None,
    state_manager=None,
    include_memory: bool = True
) -> Dict[str, Any]:
    user_input = state["user_input"]
    user_id = state["user_id"]
    session_id = state.get("session_id", "default")
    conversation_id = state.get("conversation_id")
    history = state.get("chat_history", [])

    context_data: Dict[str, Any] = {}
    if not skill_executor:
        return context_data

    try:
        emotion_result = await skill_executor.execute(
            skill_name="emotion",
            operation="analyze",
            input_data={
                "text": user_input,
                "user_id": user_id,
                "session_id": session_id,
                "context_history": history
            },
            context={"user_id": user_id, "session_id": session_id}
        )
        if emotion_result.success and emotion_result.data:
            context_data["emotion"] = emotion_result.data
    except Exception as e:
        logger.warning("emotion_analysis_failed", error=str(e))

    topic_summary = ""
    try:
        topic_result = await skill_executor.execute(
            skill_name="topic",
            operation="summarize",
            input_data={
                "history": history,
                "latest_message": user_input,
                "session_id": session_id,
                "language_hint": "zh"
            },
            context={"user_id": user_id, "session_id": session_id}
        )
        if topic_result.success and topic_result.data:
            context_data["topic"] = topic_result.data
            topic_summary = topic_result.data.get("summary", "")
    except Exception as e:
        logger.warning("topic_summary_failed", error=str(e))

    if include_memory:
        try:
            memory_result = await skill_executor.execute(
                skill_name="memory",
                operation="search",
                input_data={
                    "user_id": user_id,
                    "query": topic_summary or user_input,
                    "limit": 5,
                    "topic_summary": topic_summary,
                    "session_id": session_id
                },
                context={"user_id": user_id, "session_id": session_id}
            )
            if memory_result.success and memory_result.data:
                context_data["memories"] = memory_result.data
        except Exception as e:
            logger.warning("memory_search_failed", error=str(e))

    emotion_scores = context_data.get("emotion", {}).get("scores", {})
    ekman_scores = context_data.get("emotion", {}).get("ekman_scores", {})
    persona_id = "neutral"
    try:
        persona_result = await skill_executor.execute(
            skill_name="persona",
            operation="select",
            input_data={
                "user_id": user_id,
                "emotion_scores": emotion_scores,
                "ekman_scores": ekman_scores,
                "context_summary": topic_summary
            },
            context={"user_id": user_id, "session_id": session_id}
        )
        if persona_result.success and persona_result.data:
            context_data["persona"] = persona_result.data
            persona_id = persona_result.data.get("selected_personality", persona_id)
    except Exception as e:
        logger.warning("persona_select_failed", error=str(e))

    core_system_prompt = CORE_COMPANION_PROMPT
    try:
        persona_prompt_result = await skill_executor.execute(
            skill_name="persona",
            operation="build_system_prompt",
            input_data={
                "persona_id": persona_id,
                "core_system_prompt": core_system_prompt,
                "metadata": {"user_id": user_id, "session_id": session_id}
            },
            context={"user_id": user_id, "session_id": session_id}
        )
        if persona_prompt_result.success and persona_prompt_result.data:
            context_data["persona_prompt"] = persona_prompt_result.data.get("system_prompt")
            context_data["persona_info"] = persona_prompt_result.data.get("persona_info")
    except Exception as e:
        logger.warning("persona_prompt_failed", error=str(e))

    try:
        portrait_result = await skill_executor.execute(
            skill_name="portrait",
            operation="generate",
            input_data={
                "user_id": user_id,
                "common_settings": state.get("common_settings", {}),
                "history": history,
                "persona_id": persona_id
            },
            context={"user_id": user_id, "session_id": session_id}
        )
        if portrait_result.success and portrait_result.data:
            context_data["portrait"] = portrait_result.data
    except Exception as e:
        logger.warning("portrait_generate_failed", error=str(e))

    try:
        style_analysis = await _analyze_style(user_input, history, context_data)
        if style_analysis:
            context_data["style_analysis"] = style_analysis
    except Exception as e:
        logger.warning("style_analysis_failed", error=str(e))

    try:
        agent_thoughts = await _agent_thoughts(user_input, history, context_data)
        if agent_thoughts:
            context_data["agent_thoughts"] = agent_thoughts
    except Exception as e:
        logger.warning("agent_thoughts_failed", error=str(e))

    if state_manager and conversation_id:
        try:
            if context_data.get("emotion"):
                await state_manager.set_state(
                    state_manager.StateType.CONVERSATION,
                    conversation_id,
                    "last_emotion",
                    _extract_top_emotion(context_data["emotion"])
                )
            if persona_id:
                await state_manager.set_state(
                    state_manager.StateType.CONVERSATION,
                    conversation_id,
                    "selected_personality",
                    persona_id
                )
            if topic_summary:
                await state_manager.set_state(
                    state_manager.StateType.CONVERSATION,
                    conversation_id,
                    "topic_summary",
                    topic_summary
                )
        except Exception:
            pass

    return context_data


def _build_system_prompt(
    core_system_prompt: str,
    context_data: Dict[str, Any],
    tool_results: List[Dict[str, Any]],
    history: List[Dict[str, Any]]
) -> str:
    prompt = context_data.get("persona_prompt") or core_system_prompt

    costar_prompt = _build_costar_prompt(context_data, history)
    if costar_prompt:
        prompt += f"\n\n# FINAL GENERATION INSTRUCTION\n{costar_prompt}"

    emotion_data = context_data.get("emotion", {})
    top_emotion = _extract_top_emotion(emotion_data) if emotion_data else "neutral"
    if top_emotion:
        prompt += f"\n用户情绪: {top_emotion}"

    topic_summary = context_data.get("topic", {}).get("summary", "")
    if topic_summary:
        prompt += f"\n话题摘要: {topic_summary}"

    memories = context_data.get("memories", {}).get("memories", [])
    if memories:
        prompt += f"\n相关记忆:\n{_format_memories(memories)}"

    portrait_text = context_data.get("portrait", {}).get("portrait_text", "")
    if portrait_text:
        prompt += f"\n角色画像: {portrait_text}"

    style_rules = context_data.get("style_analysis", "")
    if style_rules:
        prompt += f"\n沟通风格规则: {style_rules}"

    agent_thoughts = context_data.get("agent_thoughts", "")
    if agent_thoughts:
        prompt += f"\n内在思考: {agent_thoughts}"

    if tool_results:
        prompt += f"\n工具结果: {tool_results}"

    return prompt


def _split_sentences(text: str) -> List[str]:
    normalized = re.sub(r"\s+", " ", (text or "")).strip()
    if not normalized:
        return []
    parts = _SENTENCE_SPLIT_RE.split(normalized)
    sentences: List[str] = []
    buffer = ""
    for part in parts:
        if not part:
            continue
        if _SENTENCE_SPLIT_RE.fullmatch(part):
            buffer += part
            if buffer.strip():
                sentences.append(buffer.strip())
            buffer = ""
        else:
            buffer += part
    if buffer.strip():
        sentences.append(buffer.strip())
    return sentences


async def _compress_response_to_limit(
    text: str,
    user_input: str,
    context_data: Dict[str, Any]
) -> str:
    if len(_split_sentences(text)) <= 2:
        return text
    top_emotion = "neutral"
    if context_data.get("emotion"):
        top_emotion = _extract_top_emotion(context_data["emotion"])
    portrait_text = context_data.get("portrait", {}).get("portrait_text", "")
    style_rules = context_data.get("style_analysis", "")
    agent_thoughts = context_data.get("agent_thoughts", "")

    compress_prompt = (
        "请把原回复压缩为1-2句，保证语义完整、情感温度与连贯性。"
        "不要添加新信息，不要列表或分段，只输出最终回复正文。"
        f"\n用户输入: {user_input}"
        f"\n原回复: {text}"
        f"\n用户情绪: {top_emotion}"
        f"\n角色画像: {portrait_text}"
        f"\n沟通风格规则: {style_rules}"
        f"\n内在思考: {agent_thoughts}"
    )

    llm = _create_llm(0.2)
    try:
        compressed = await llm.ainvoke([
            SystemMessage(content="你是对话压缩器，优先保持语义与情感一致。"),
            HumanMessage(content=compress_prompt)
        ])
        result = (compressed.content or text).strip()
    except Exception as e:
        logger.warning("response_compress_failed", error=str(e))
        return text

    if len(_split_sentences(result)) > 2:
        return text
    return result


async def _refine_response(
    draft: str,
    user_input: str,
    context_data: Dict[str, Any]
) -> str:
    if not draft:
        return draft

    top_emotion = "neutral"
    if context_data.get("emotion"):
        top_emotion = _extract_top_emotion(context_data["emotion"])
    topic_summary = context_data.get("topic", {}).get("summary", "")
    memories = context_data.get("memories", {}).get("memories", [])
    portrait_text = context_data.get("portrait", {}).get("portrait_text", "")
    style_rules = context_data.get("style_analysis", "")
    agent_thoughts = context_data.get("agent_thoughts", "")

    refinement_prompt = (
        "请基于以下信息改进回复质量，使其更具拟人化特征："
        "\n1. 使用自然口语化表达，避免机械式回答"
        "\n2. 适当使用语气词（如呢、呀、吧、哦）增强亲和力"
        "\n3. 根据用户情绪调整语气（悲伤时温柔，开心时活泼）"
        "\n4. 加入个人化表达，体现独特性格"
        "\n5. 保持同理心，展现情感共鸣"
        "\n6. 避免重复，保持对话连贯性"
        "\n7. 回复严格控制在1-2句内，保持聊天风格"
        "\n只输出最终回复正文。"
        f"\n用户输入: {user_input}"
        f"\n草稿回复: {draft}"
        f"\n用户情绪: {top_emotion}"
        f"\n话题摘要: {topic_summary}"
        f"\n相关记忆: {_format_memories(memories)}"
        f"\n角色画像: {portrait_text}"
        f"\n沟通风格规则: {style_rules}"
        f"\n内在思考: {agent_thoughts}"
    )

    llm = _create_llm(0.4)
    try:
        refined = await llm.ainvoke([
            SystemMessage(content="你是拟人化回复优化器，目标是让回复更像真人对话，充满情感温度和个性魅力。"),
            HumanMessage(content=refinement_prompt)
        ])
        refined_text = refined.content or draft
    except Exception:
        refined_text = draft

    return await _compress_response_to_limit(refined_text, user_input, context_data)


async def _persist_memory(
    user_input: str,
    response_text: str,
    user_id: str,
    session_id: str,
    context_data: Dict[str, Any],
    skill_executor=None
) -> None:
    if not skill_executor or not response_text:
        return
    try:
        metadata = {
            "emotion": context_data.get("emotion", {}),
            "persona": context_data.get("persona", {}),
            "topic": context_data.get("topic", {})
        }
        await skill_executor.execute(
            skill_name="memory",
            operation="add",
            input_data={
                "user_id": user_id,
                "text": f"User: {user_input}\nAI: {response_text}",
                "metadata": metadata,
                "session_id": session_id
            },
            context={"user_id": user_id, "session_id": session_id}
        )
    except Exception:
        return


async def standard_generate(
    state: AgentState,
    skill_executor=None,
    flow_orchestrator=None,
    state_manager=None
) -> Dict[str, Any]:
    user_input = state["user_input"]
    user_id = state["user_id"]
    session_id = state.get("session_id", "default")
    raw_history = state.get("chat_history", [])
    history = _convert_history(raw_history)

    context_data = await _collect_context(
        state,
        skill_executor=skill_executor,
        state_manager=state_manager,
        include_memory=True
    )

    system_prompt = _build_system_prompt(
        _companion_prompt(
            "回复时请使用自然口语化表达，适当加入语气词，展现情感温度和个性魅力。"
        ),
        context_data,
        [],
        raw_history
    )

    llm = _create_llm(0.75)
    messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=user_input)]

    logger.info("Daisy_skills Generation Prompt",
                system_prompt=system_prompt,
                messages_count=len(messages),
                user_input=user_input)

    try:
        response = await llm.ainvoke(messages)
    except Exception as e:
        logger.error("llm_invoke_failed", error=str(e))
        _persist_llm_trace(
            user_id=str(user_id),
            agent_name="SkillsGeneration.standard",
            trigger_message=user_input,
            system_prompt=system_prompt,
            user_input=user_input,
            response=None,
            error=str(e)
        )
        return {"response": "I'm sorry, I encountered an error."}

    draft = response.content
    _persist_llm_trace(
        user_id=str(user_id),
        agent_name="SkillsGeneration.standard",
        trigger_message=user_input,
        system_prompt=system_prompt,
        user_input=user_input,
        response=draft,
        error=None
    )
    refined = await _refine_response(draft, user_input, context_data)
    await _persist_memory(user_input, refined, user_id, session_id, context_data, skill_executor)
    return {"response": refined}


async def context_aware_generate(
    state: AgentState,
    skill_executor=None,
    flow_orchestrator=None,
    state_manager=None
) -> Dict[str, Any]:
    user_input = state["user_input"]
    user_id = state["user_id"]
    session_id = state.get("session_id", "default")
    raw_history = state.get("chat_history", [])
    history = _convert_history(raw_history)

    context_data = await _collect_context(
        state,
        skill_executor=skill_executor,
        state_manager=state_manager,
        include_memory=True
    )

    system_prompt = _build_system_prompt(
        _companion_prompt(
            "此轮对话中优先处理用户情绪与陪伴安抚。"
            "回复时请使用自然口语化表达，适当加入语气词，展现情感温度和个性魅力。"
        ),
        context_data,
        [],
        raw_history
    )

    llm = _create_llm(0.85)
    messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=user_input)]

    logger.info("Daisy_skills Generation Prompt",
                system_prompt=system_prompt,
                messages_count=len(messages),
                user_input=user_input,
                route="context_aware")

    try:
        response = await llm.ainvoke(messages)
    except Exception as e:
        logger.error("context_aware_llm_invoke_failed", error=str(e))
        _persist_llm_trace(
            user_id=str(user_id),
            agent_name="SkillsGeneration.context_aware",
            trigger_message=user_input,
            system_prompt=system_prompt,
            user_input=user_input,
            response=None,
            error=str(e)
        )
        return {"response": "I'm sorry, I encountered an error."}

    draft = response.content
    _persist_llm_trace(
        user_id=str(user_id),
        agent_name="SkillsGeneration.context_aware",
        trigger_message=user_input,
        system_prompt=system_prompt,
        user_input=user_input,
        response=draft,
        error=None
    )
    refined = await _refine_response(draft, user_input, context_data)
    await _persist_memory(user_input, refined, user_id, session_id, context_data, skill_executor)
    return {"response": refined}


async def tool_required_generate(
    state: AgentState,
    skill_executor=None,
    flow_orchestrator=None,
    state_manager=None
) -> Dict[str, Any]:
    user_input = state["user_input"]
    user_id = state["user_id"]
    session_id = state.get("session_id", "default")
    raw_history = state.get("chat_history", [])
    history = _convert_history(raw_history)

    tool_results: List[Dict[str, Any]] = []

    if skill_executor:
        if "搜索" in user_input or "查询" in user_input:
            try:
                search_result = await skill_executor.execute(
                    skill_name="toolhub",
                    operation="search",
                    input_data={"query": user_input, "top_k": 5, "locale": "zh"},
                    context={"user_id": user_id, "session_id": session_id}
                )
                if search_result.success:
                    tool_results.append({"skill": "toolhub.search", "result": search_result.data})
            except Exception as e:
                logger.warning("toolhub_search_failed", error=str(e))

        if any(ch.isdigit() for ch in user_input) and any(op in user_input for op in ["+", "-", "*", "/", "×", "÷"]):
            expression = "".join(c for c in user_input.replace("×", "*").replace("÷", "/") if c in "0123456789+-*/(). ")
            if expression.strip():
                try:
                    calc_result = await skill_executor.execute(
                        skill_name="toolhub",
                        operation="calculate",
                        input_data={"expression": expression.strip()},
                        context={"user_id": user_id, "session_id": session_id}
                    )
                    if calc_result.success:
                        tool_results.append({"skill": "toolhub.calculate", "result": calc_result.data})
                except Exception as e:
                    logger.warning("toolhub_calculate_failed", error=str(e))

        if "天气" in user_input:
            try:
                weather_result = await skill_executor.execute(
                    skill_name="toolhub",
                    operation="weather",
                    input_data={"location": user_input, "days": 1},
                    context={"user_id": user_id, "session_id": session_id}
                )
                if weather_result.success:
                    tool_results.append({"skill": "toolhub.weather", "result": weather_result.data})
            except Exception as e:
                logger.warning("toolhub_weather_failed", error=str(e))

        if "记住" in user_input or "保存" in user_input:
            try:
                memory_result = await skill_executor.execute(
                    skill_name="memory",
                    operation="add",
                    input_data={"user_id": user_id, "text": user_input, "session_id": session_id},
                    context={"user_id": user_id, "session_id": session_id}
                )
                if memory_result.success:
                    tool_results.append({"skill": "memory.add", "result": memory_result.data})
            except Exception as e:
                logger.warning("memory_add_failed", error=str(e))

    context_data = await _collect_context(
        state,
        skill_executor=skill_executor,
        state_manager=state_manager,
        include_memory=True
    )

    system_prompt = _build_system_prompt(
        _companion_prompt(
            "在提供工具结果时保持情感陪伴语气与温度。"
            "回复时请使用自然口语化表达，适当加入语气词，展现情感温度和个性魅力。"
        ),
        context_data,
        tool_results,
        raw_history
    )

    llm = _create_llm(0.75)
    messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=user_input)]

    logger.info("Daisy_skills Generation Prompt",
                system_prompt=system_prompt,
                messages_count=len(messages),
                user_input=user_input,
                route="tool_required")

    try:
        response = await llm.ainvoke(messages)
    except Exception as e:
        logger.error("tool_required_llm_invoke_failed", error=str(e))
        _persist_llm_trace(
            user_id=str(user_id),
            agent_name="SkillsGeneration.tool_required",
            trigger_message=user_input,
            system_prompt=system_prompt,
            user_input=user_input,
            response=None,
            error=str(e)
        )
        return {"response": "I'm sorry, I encountered an error."}

    draft = response.content
    _persist_llm_trace(
        user_id=str(user_id),
        agent_name="SkillsGeneration.tool_required",
        trigger_message=user_input,
        system_prompt=system_prompt,
        user_input=user_input,
        response=draft,
        error=None
    )
    refined = await _refine_response(draft, user_input, context_data)
    await _persist_memory(user_input, refined, user_id, session_id, context_data, skill_executor)
    return {"response": refined}


async def quick_generate(
    state: AgentState,
    skill_executor=None,
    flow_orchestrator=None,
    state_manager=None
) -> Dict[str, Any]:
    user_input = state["user_input"]
    user_id = state["user_id"]
    session_id = state.get("session_id", "default")

    quick_responses = {
        "hi": "Hi，我在呢。今天感觉怎么样？",
        "hello": "Hello，我在这里陪你。有什么想聊的吗？",
        "ok": "好的，我会一直在。",
        "yes": "太好了，我们继续聊。",
        "no": "没关系，我陪你，随时可以再说。"
    }

    lower_input = user_input.lower().strip()
    if lower_input in quick_responses:
        return {"response": quick_responses[lower_input]}

    raw_history = state.get("chat_history", [])
    history = _convert_history(raw_history)
    context_data = await _collect_context(
        state,
        skill_executor=skill_executor,
        state_manager=state_manager,
        include_memory=False
    )

    system_prompt = _build_system_prompt(
        _companion_prompt(
            "保持简短、温柔与陪伴感。"
            "回复时请使用自然口语化表达，适当加入语气词，展现情感温度和个性魅力。"
        ),
        context_data,
        [],
        raw_history
    )

    llm = _create_llm(0.65)
    messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=user_input)]

    try:
        response = await llm.ainvoke(messages)
    except Exception as e:
        logger.error("quick_llm_invoke_failed", error=str(e))
        _persist_llm_trace(
            user_id=str(user_id),
            agent_name="SkillsGeneration.quick",
            trigger_message=user_input,
            system_prompt=system_prompt,
            user_input=user_input,
            response=None,
            error=str(e)
        )
        return {"response": "I'm sorry, I encountered an error."}

    draft = response.content
    _persist_llm_trace(
        user_id=str(user_id),
        agent_name="SkillsGeneration.quick",
        trigger_message=user_input,
        system_prompt=system_prompt,
        user_input=user_input,
        response=draft,
        error=None
    )
    refined = await _refine_response(draft, user_input, context_data)
    await _persist_memory(user_input, refined, user_id, session_id, context_data, skill_executor)
    return {"response": refined}
