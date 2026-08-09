"""
通用设置(用户/角色的基础设定)与由它生成系统提示词的接口。

从原 config.py 拆出,见 llm_config.py 的说明。URL 路径不变。
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, List, Any
import json
import os
import structlog

from app.core.database import get_db
from app.core.config import settings
from app.core.cache import redis_client
from app.models import UserDB, CommonSettingsDB, RoleProfileDB
from app.prompts import CommonSettings, RoleProfile, get_system_prompt_generator_meta
from app.api.deps import get_current_user
from app.core.llm import get_llm_service
from app.services.dialogue.generation import generate_character_portrait_async, generate_deep_character_card

logger = structlog.get_logger()
router = APIRouter()

@router.post("/generate_prompt")
async def generate_prompt(common: CommonSettings):
    """
    基于通用设置使用 LLM 生成系统提示词 (System Prompt)。
    """
    llm = get_llm_service()
    if not common.llm_api_key and not common.llm_provider and not settings.DEFAULT_LLM_PROVIDER:
         raise HTTPException(status_code=400, detail="LLM_NOT_CONFIGURED")
         
    meta_prompt = get_system_prompt_generator_meta()
    
    # 构造更完整、准确的输入，包含核心约束
    user_input = f"""
    Based on the following settings, generate a CO-STAR system prompt:
    
    Name: {common.name}
    Gender: {common.gender or "Not specified"}
    Age: {common.age or "Not specified"}
    Occupation (Role): {common.occupation or "Not specified"}
    Relationship with User: {common.relationship or "Friend"}
    Backstory: {common.backstory or "None"}
    World Setting: {common.world_setting or "Modern Real World"}
    
    IMPORTANT: The following Core System Instructions will be PREPENDED to your generated prompt at runtime. 
    To avoid redundancy and token waste, DO NOT repeat these basic rules in your output unless you want to override them with a specific personality trait.
    Focus your generated prompt on the unique Personality, Tone, and Relationship dynamics.
    
    [Core System Instructions]:
    {common.core_system_prompt or "Default: 1. No AI disclosure. 2. Chinese language. 3. Natural spoken language."}
    """
    
    try:
        response = llm.generate_response(
            system_prompt=meta_prompt,
            user_input=user_input,
            context="",
            user_settings=common,
            metadata={"agent_name": "SystemPromptGenerator"}
        )
        return {"prompt": response}
    except ValueError as e:
        if str(e) == "LLM_NOT_CONFIGURED":
             raise HTTPException(status_code=400, detail="LLM_NOT_CONFIGURED")
        raise e

@router.get("/common", response_model=CommonSettings)
async def get_common_settings(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    """
    获取当前用户的通用设置。
    """
    settings = db.query(CommonSettingsDB).filter(CommonSettingsDB.user_id == current_user.id).first()
    if not settings:
        return CommonSettings()
    
    return CommonSettings(
        name=settings.name,
        gender=settings.gender,
        age=settings.age,
        occupation=settings.occupation,
        relationship=settings.relationship,
        backstory=settings.backstory,
        world_setting=settings.world_setting,
        system_prompt_template=settings.system_prompt_template,
        core_system_prompt=settings.core_system_prompt,
        llm_provider=settings.llm_provider,
        llm_api_key=settings.llm_api_key,
        llm_base_url=settings.llm_base_url,
        llm_model_name=settings.llm_model_name,
        has_character_card=bool(settings.character_card_json),
        avatar_path=settings.avatar_path,
        user_avatar_path=settings.user_avatar_path,
        background_image_path=settings.background_image_path
    )

@router.post("/common")
async def update_common_settings(
    settings: CommonSettings,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    """
    更新通用设置。
    """
    db_settings = db.query(CommonSettingsDB).filter(CommonSettingsDB.user_id == current_user.id).first()
    if not db_settings:
        db_settings = CommonSettingsDB(user_id=current_user.id)
        db.add(db_settings)
    
    db_settings.name = settings.name
    db_settings.gender = settings.gender
    db_settings.age = settings.age
    db_settings.occupation = settings.occupation
    db_settings.relationship = settings.relationship
    db_settings.backstory = settings.backstory
    db_settings.world_setting = settings.world_setting
    db_settings.system_prompt_template = settings.system_prompt_template
    db_settings.core_system_prompt = settings.core_system_prompt
    db_settings.avatar_path = settings.avatar_path
    db_settings.user_avatar_path = settings.user_avatar_path
    db_settings.background_image_path = settings.background_image_path
    
    if settings.llm_provider and settings.llm_provider != db_settings.llm_provider:
        db_settings.llm_provider = settings.llm_provider
        db_settings.llm_api_key = None
        db_settings.llm_base_url = None
        db_settings.llm_model_name = None
        logger.info(f"LLM Provider switched to {settings.llm_provider}. Custom settings cleared.")
        # 记忆抽取跟随对话 provider,而 MemoryService 是 @lru_cache 单例、
        # provider 在首次构造时定死 —— 不清缓存的话,换了服务商记忆仍走旧的。
        try:
            from app.services.memory.store import get_memory_service
            get_memory_service.cache_clear()
        except Exception as e:
            logger.warning(f"Failed to clear MemoryService cache after provider switch: {e}")

    if settings.llm_api_key:
        db_settings.llm_api_key = settings.llm_api_key
    if settings.llm_base_url:
        db_settings.llm_base_url = settings.llm_base_url
    if settings.llm_model_name:
        db_settings.llm_model_name = settings.llm_model_name
    
    # 角色卡:先保证「有卡可用」,再谈「卡好不好」。
    #
    # 原实现在这里内联 await 深度生成,既无超时也无兜底:模型慢一点(深度卡输出
    # 2000+ tokens,常超过通用 60s 超时)就返回 None,character_card_json 保持
    # NULL,前端门禁永不解除 —— 表现为「角色卡生成中」一直转圈,且请求本身被
    # 阻塞两分钟。改为:无卡时立刻落默认卡解除门禁,深度生成移到后台静默升级。
    if not db_settings.character_card_json:
        try:
            from app.services.persona.character_card import load_default_character_card
            baseline = load_default_character_card()
            if baseline:
                db_settings.character_card_json = baseline.model_dump()
                logger.info(f"Applied default character card for user {current_user.id} (unblocks chat now)")
        except Exception as e:
            logger.error(f"Failed to apply baseline character card: {e}")

    # 深度生成复用 auth.generate_card_background(自带超时 + 失败保留默认卡)。
    # 本 bug 的成因正是两条路径各写各的,这里不再造第三份实现。
    from app.api.auth import generate_card_background
    background_tasks.add_task(generate_card_background, current_user.id)

    try:
        should_use_cache = False
        cache_key = f"portrait_default:{settings.name}"
        cached_portrait = await redis_client.get(cache_key)
        
        if cached_portrait:
             base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
             settings_path = os.path.join(base_dir, "default_settings.json")
             if os.path.exists(settings_path):
                 with open(settings_path, "r", encoding="utf-8") as f:
                     defaults = json.load(f)
                     matched_default = None
                     for key, val in defaults.items():
                         if val.get("name") == settings.name:
                             matched_default = val
                             break
                     
                     if matched_default:
                         is_same = True
                         for field in ["age", "gender", "occupation", "backstory", "world_setting"]:
                             val1 = getattr(settings, field, None) or ""
                             val2 = matched_default.get(field, "") or ""
                             if str(val1).strip() != str(val2).strip():
                                 is_same = False
                                 break
                         if is_same:
                             should_use_cache = True
        
        if should_use_cache:
            db_settings.portrait = cached_portrait
            logger.info(f"Using cached portrait for {settings.name}")
        else:
            generated_portrait = await generate_character_portrait_async(current_user.id, settings)
            db_settings.portrait = generated_portrait

    except Exception as e:
        logger.error(f"Failed to generate portrait during settings update: {e}")
    
    db.commit()
    db.refresh(db_settings)
    return {"status": "success"}
