from app.core.llm import get_llm_service
from app.services.memory.topic_agent import topic_agent
from app.prompts import (
    CommonSettings, 
    RoleProfile, 
    get_character_portrait_prompt, 
    get_style_analysis_prompt, 
    get_topic_summary_prompt
)
from app.agents.daisy.character_card import CharacterCard
from app.core.database import SessionLocal
from app.models import ChatHistoryDB
from app.core.utils import group_chat_history_by_pairs
from app.core.cache import redis_client
from app.core.config import settings
from app.core.json_utils import parse_llm_json
from app.core.constants import (
    STYLE_ANALYSIS_CACHE_TTL,
    MULTI_AGENT_ACTIVE_THRESHOLD,
    MULTI_AGENT_TOP_PERSONAS_COUNT
)
import datetime
import structlog
import json
import re
from app.multi_agent import multi_agent_service
from typing import Dict, List, Tuple, Any, Optional
from app.prompts import RoleProfile

logger = structlog.get_logger()

async def generate_deep_character_card(common: CommonSettings) -> Optional[CharacterCard]:
    """
    Step 1.2: 深度角色生成器 (Character Generator)
    基于 CommonSettings 中的简单信息，利用 LLM 的逻辑推演，生成完整的深度角色卡。
    """
    
    # 1. 构造 Prompt
    system_prompt = """
    # Role: Deep Character Profiler & Novelist
    你是一位擅长心理侧写的小说家。你的任务是将用户提供的简单人物设定（姓名、职业、年龄）扩写成一份具有文学深度、逻辑自洽的完整角色档案。
    
    # Core Philosophy
    1. **Anti-Cliché (反套路)**: 不要默认高官就是霸道，医生就是洁癖。寻找“意料之外，情理之中”的设定。
    2. **Logical Deduction (逻辑推演)**: 每一个性格特征必须有来源 (Backstory)。如果他冷漠，是因为受过伤，还是天生迟钝？
    3. **Complexity (复杂性)**: 人是矛盾的。为角色设计“表层面具”和“深层底色”的反差。
    
    # Output Format
    你必须输出一个符合特定 JSON Schema 的 JSON 对象。不要包含任何 Markdown 格式（如 ```json）。
    
    # Schema Definition
    {
      "identity": {
        "name": "...", "gender": "...", "age": 25, 
        "occupation": "...", "mbti": "..."
      },
      "personality": {
        "description": "...", "core_traits": ["..."]
      },
      "language_style": {
        "tone": "...", "quirks": ["..."], 
        "common_phrases": {
            "greeting": ["..."], 
            "agreement": ["..."], 
            "thinking": ["..."]
        }
      },
      "context": {
        "backstory": "...", "world_setting": "..."
      },
      "constraints": [
        {"type": "...", "description": "...", "coping_strategy": ["..."]}
      ],
      "behavior": {
        "push_pull_pattern": {
            "description": "...", 
            "pull_behaviors": ["..."], 
            "push_behaviors": ["..."]
        }
      },
      "relationship_dynamics": [
        {"level": 1, "name": "...", "description": "...", "prompt_addon": "..."}
      ],
      "dialogue_examples": [
        {"scene": "...", "user": "...", "agent": "..."}
      ],
      "inner_monologue_patterns": [
        {"emotion": "...", "pattern": "..."}
      ]
    }
    """
    
    user_input = f"""
    请基于以下种子信息生成角色卡：
    - Name: {common.name}
    - Gender: {common.gender}
    - Age: {common.age}
    - Occupation: {common.occupation}
    - Backstory Hint: {common.backstory or "N/A"}
    - World Setting: {common.world_setting or "Modern Realism"}
    """
    
    llm = get_llm_service()
    try:
        # 调用 LLM (推荐使用较强的模型如 gpt-4o 或 deepseek-v3)
        # 专用超时:角色卡是一次性的大输出(实测 2000+ tokens),通用 60s 聊天超时
        # 太紧 —— 60s 超时 + 1 次重试 = 122s 才失败,比外层 DEEP_CARD_TIMEOUT_SEC
        # 还长,导致外层保护形同虚设。这里单次给足时间且不重试:失败了有默认卡兜底,
        # 重试只会让用户多等一倍。
        _timeout = settings.DEEP_CARD_LLM_TIMEOUT_SEC
        if hasattr(llm, "generate_response_async"):
            response_text = await llm.generate_response_async(
                system_prompt=system_prompt,
                user_input=user_input,
                context="",
                user_settings=common,
                metadata={"agent_name": "DeepCharacterGenerator"},
                request_timeout=_timeout,
                max_retries=0,
            )
        else:
            # Fallback sync
            response_text = llm.generate_response(
                system_prompt=system_prompt, user_input=user_input, context="",
                user_settings=common, metadata={"agent_name": "DeepCharacterGenerator"},
                request_timeout=_timeout, max_retries=0,
            )
            
        # 2. 清洗与解析 JSON
        data = parse_llm_json(response_text)
        
        # Inject avatar_path if provided in common settings
        if common.avatar_path and "identity" in data:
             data["identity"]["avatar_path"] = common.avatar_path

        # 3. 验证与转换 (Pydantic)
        card = CharacterCard(**data)
        logger.info(f"Generated deep character card for {common.name}")
        return card
        
    except Exception as e:
        logger.error(f"Failed to generate deep character card: {e}")
        return None

def generate_character_portrait(common: CommonSettings) -> str:
    """
    任务 1: 角色画像
    基于通用设置生成“角色画像”。
    """
    portrait_prompt = get_character_portrait_prompt(common)
    
    llm = get_llm_service()
    generated_portrait = f"{common.name} is a {common.age}-year-old {common.gender} {common.occupation}."
    try:
        # 直接调用 generate_response，让其内部处理配置加载和兜底逻辑
        generated_portrait = llm.generate_response(
            system_prompt="You are an expert character profiler.",
            user_input=portrait_prompt,
            context="",
            user_settings=common,
            metadata={"trigger_message": "Generate Character Portrait", "agent_name": "ProfileAgent", "execution_id": None}
        )
    except Exception as e:
        logger.error(f"Failed to generate character portrait: {e}")
            
    return generated_portrait

async def generate_character_portrait_async(user_id: int, common: CommonSettings, execution_id: str = None) -> str:
    """
    generate_character_portrait 的异步版本
    """
    raw_info = f"""
    Name: {common.name}
    Gender: {common.gender}
    Age: {common.age}
    Occupation: {common.occupation}
    World Setting: {common.world_setting}
    Backstory: {common.backstory}
    """
    
    portrait_prompt = f"""
    基于以下原始信息合成一个“角色画像”。
    
    **原始信息**:
    {raw_info}
    
    **目标**:
    创建一个简洁、整合的段落（约100-150字），捕捉角色的本质。
    将事实（年龄、工作、学校）与背景故事中提到的个性特征和矛盾融合在一起。
    
    **示例输出风格**:
    "静雯是一位24岁的心理学家，生活在2025年的武汉。她将小镇出身的温柔与顶尖医学院的学术严谨相结合..."
    
    用中文输出角色画像。
    """
    
    llm = get_llm_service()
    generated_portrait = f"{common.name} is a {common.age}-year-old {common.gender} {common.occupation}."
    
    # 如果有异步方法则使用，否则在 executor 中运行
    try:
        if hasattr(llm, "generate_response_async"):
            generated_portrait = await llm.generate_response_async(
                system_prompt="你是一位专家级的人物画像分析师。",
                user_input=portrait_prompt,
                context="",
                user_settings=common,
                metadata={"trigger_message": "Generate Character Portrait", "agent_name": "ProfileAgent", "user_id": user_id, "execution_id": execution_id}
            )
        else:
            # 回退到 executor 中的同步执行
            import asyncio
            loop = asyncio.get_event_loop()
            generated_portrait = await loop.run_in_executor(
                None, 
                llm.generate_response,
                "你是一位专家级的人物画像分析师。",
                portrait_prompt,
                "",
                common,
                {"trigger_message": "Generate Character Portrait", "agent_name": "ProfileAgent", "user_id": user_id, "execution_id": execution_id}
            )
    except Exception as e:
        logger.error(f"Failed to generate character portrait async: {e}")
            
    return generated_portrait

async def generate_style_analysis(user_id: str, common: CommonSettings, mix_names: List[str], user_input: str, trigger_message_id: int = None, active_profiles: List[Any] = None, execution_id: str = None) -> str:
    """
    任务 2: 风格分析
    """
    cache_key = f"style_analysis:{user_id}"
    cached = await redis_client.get(cache_key)
    if cached:
        return cached

    prompt = get_style_analysis_prompt(common, mix_names)
    llm = get_llm_service()
    
    style_analysis = "Style analysis unavailable."
    try:
        if hasattr(llm, "generate_response_async"):
            style_analysis = await llm.generate_response_async(
                system_prompt="你是一位性格分析师。",
                user_input=prompt,
                context=f"User Input: {user_input}",
                user_settings=common,
                metadata={"trigger_message": user_input, "agent_name": "StyleAgent", "user_id": user_id, "execution_id": execution_id},
                max_retries=3
            )
        else:
             import asyncio
             loop = asyncio.get_event_loop()
             style_analysis = await loop.run_in_executor(
                None,
                llm.generate_response,
                "你是一位性格分析师。",
                prompt,
                f"User Input: {user_input}",
                common,
                {"trigger_message": user_input, "agent_name": "StyleAgent", "user_id": user_id, "execution_id": execution_id}
             )
        
        if style_analysis and "Error" not in style_analysis:
            await redis_client.set(cache_key, style_analysis, ttl=STYLE_ANALYSIS_CACHE_TTL)
            
    except Exception as e:
        logger.error(f"Failed to generate style analysis: {e}")
        style_analysis = f"Error generating style: {e}"
            
    return style_analysis

async def generate_topic_summary(user_id: str, common: CommonSettings, current_input: str, trigger_message_id: int = None, execution_id: str = None) -> str:
    """
    任务 4: 上下文与历史记录 (话题识别)
    Delegate to TopicAnalysisAgent.
    """
    try:
        return await topic_agent.run(user_id, common, current_input, trigger_message_id, execution_id=execution_id)
    except Exception as e:
        logger.error(f"Failed to generate topic summary via Agent: {e}")
        # 重新抛出异常以便上层捕获
        raise e

async def generate_agent_thoughts(
    user_input: str, 
    user_id: str, 
    weights: Dict[str, float], 
    selected_personality: str, 
    context_text: str = "", 
    portrait_text: str = "", 
    trigger_message_id: int = None,
    active_profiles_list: List[Tuple[RoleProfile, float]] = None,
    state: Dict[str, Any] = None
) -> Dict[str, str]:
    """
    任务 3: 内部思维 (MultiAgent 并发)
    """
    # 供预算账本记账;state 里没有就为 None(不计数,与旧行为一致)
    execution_id = (state or {}).get("execution_id")
    if not weights:
        # 如果权重缺失，则回退到选定的性格
        if selected_personality:
            weights = {selected_personality: 1.0}
        else:
            return {}

    # 排序并选择前 3 名
    sorted_weights = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    
    # 选择活跃人格: > 15% 或至少前 1 名
    top_personas = [p for p in sorted_weights if p[1] > MULTI_AGENT_ACTIVE_THRESHOLD][:MULTI_AGENT_TOP_PERSONAS_COUNT] 
    
    # 如果没有人超过 15% (罕见)，则取第一名
    if not top_personas and sorted_weights:
        top_personas = [sorted_weights[0]]
    
    active_names = [name for name, _ in top_personas]
    
    
    try:
        # 使用新的异步 Lite MultiAgent 服务
        # 替代原有的 Multi-Agent 框架，直接并发调用 LLM
        thoughts = await multi_agent_service.consult_personalities_async(
            user_input,
            active_names,
            user_id,
            context_text,
            portrait_text,
            trigger_message_id,
            execution_id=execution_id,
        )
        return thoughts
        
    except Exception as e:
        logger.error(f"Agent Thoughts Generation failed: {e}")
        return {}
