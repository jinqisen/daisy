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

@router.get("/providers")
async def get_llm_providers():
    """
    获取可用的 LLM 提供商列表。
    """
    # app/api/routers/config.py -> app/api/routers -> app/api -> app -> Daisy_server
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    config_path = os.path.join(base_dir, "llm_providers.json")
    
    if not os.path.exists(config_path):
        logger.warning(f"LLM providers config not found at {config_path}")
        return {}
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            file_providers = json.load(f)
            
        result_providers = {}
        
        for pid in file_providers.keys():
            redis_key = f"system:llm:provider:{pid}"
            try:
                cached = await redis_client.get(redis_key)
                if cached:
                    provider_data = json.loads(cached)
                    if "api_key" in provider_data:
                        del provider_data["api_key"]
                    result_providers[pid] = provider_data
                else:
                    result_providers[pid] = file_providers[pid]
            except Exception as e:
                logger.error(f"Error fetching provider {pid} from Redis: {e}")
                result_providers[pid] = file_providers[pid]
                
        return result_providers

    except Exception as e:
        logger.error(f"Failed to load LLM providers config: {e}")
        return {}


# ---- 系统级 LLM 密钥(本地 C 端:用户自填密钥)----
# 用户级 llm_api_key 只作用于最终生成;流水线内多个 agent(router/记忆/策略/话题/画像/
# reflexion)用系统默认 provider,其 key 来自 env。故需要一个系统级入口:把用户填的 key
# 注入 env + 持久化到用户配置文件 + 热重载 provider,使全链路都能用。

# provider 环境变量名映射(与 llm_providers.json 的 api_key_env 一致)
_KEY_ENV_NAMES = ["MAAS_API_KEY", "SILICONFLOW_API_KEY", "OPENAI_API_KEY", "HUAWEI_SEARCH_API_KEY"]


def _user_config_path() -> str:
    """密钥持久化目标:优先 DAISY_CONFIG_PATH(桌面版指向用户目录),否则源码树。"""
    p = os.environ.get("DAISY_CONFIG_PATH")
    if p:
        return p
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(base_dir, "server_config.json")


@router.get("/llm_keys")
async def get_llm_keys(current_user: UserDB = Depends(get_current_user)):
    """返回各密钥是否已配置(不回传明文)。"""
    return {name: bool(os.environ.get(name)) for name in _KEY_ENV_NAMES}


@router.get("/llm_status")
async def get_llm_status(current_user: UserDB = Depends(get_current_user)):
    """
    LLM 配置状态摘要(不含密钥明文)。前端据此判断:
    角色卡缺失时究竟是"正在生成"还是"尚未配置模型" —— 后者应引导用户去填 API Key,
    而不是显示无限加载。任何已登录用户可访问(桌面版普通用户也需要能完成首次配置)。
    """
    from app.core.llm_config import llm_config_status
    return llm_config_status()


@router.post("/llm_keys")
async def set_llm_keys(payload: Dict[str, str], current_user: UserDB = Depends(get_current_user)):
    """
    设置系统级 LLM 密钥(用户自填)。持久化到用户配置文件 + 注入 env + 热重载 provider,
    无需重启即生效于全链路。payload 例:{"MAAS_API_KEY": "...", "SILICONFLOW_API_KEY": "..."}
    """
    from app.services.system.init_data import load_llm_providers_to_redis

    updates = {k: v for k, v in payload.items() if k in _KEY_ENV_NAMES and isinstance(v, str) and v.strip()}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid keys provided")

    # 0. 保存前探活。原本照单全收 —— 填错服务的密钥也会落盘,要等第一次对话
    #    失败才暴露,而那时的表现是"角色卡一直生成中",用户根本联想不到是密钥
    #    填错了槽位(实测:一把搜索密钥被填进了聊天密钥的位置)。
    #    只有**明确的认证失败**才拒绝;超时/限流/断网一律放行,否则离线场景配不上。
    from app.services.system.key_verification import verify_key, VALID, INVALID

    verdicts = {}
    for name, value in updates.items():
        status, reason = await verify_key(name, value)
        verdicts[name] = {"status": status, "reason": reason}
        logger.info(f"Key probe {name}: {status} ({reason})")

    rejected = {k: v["reason"] for k, v in verdicts.items() if v["status"] == INVALID}
    if rejected:
        detail = "；".join(f"{k}: {r}" for k, r in rejected.items())
        raise HTTPException(status_code=400, detail=detail)

    # 1. 注入进程环境(立即对 load_llm_providers_to_redis 生效)
    for k, v in updates.items():
        os.environ[k] = v.strip()

    # 1b. 同步更新 settings 单例:settings 是启动时快照,部分模块(如 memory 的
    # embedder)直接读它;不同步会导致这些模块拿不到运行期填入的密钥。
    for k, v in updates.items():
        if hasattr(settings, k):
            try:
                setattr(settings, k, v.strip())
            except Exception as e:
                logger.warning(f"Failed to sync {k} into settings: {e}")

    # 2. 持久化到用户配置文件(重启后由 config 启动逻辑重新加载)
    cfg_path = _user_config_path()
    try:
        data = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        data.update(updates)
        os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to persist LLM keys to {cfg_path}: {e}")
        raise HTTPException(status_code=500, detail="Failed to persist keys")

    # 3. 清除"密钥失效"标记 —— 用户刚填了新密钥,应给它一次机会,
    #    否则旧密钥的失效记录会让新密钥也被判为不可用。
    from app.core.llm_config import clear_invalid_marks
    clear_invalid_marks()

    # 4. 热重载所有 provider,使内部 agent 立即拿到新 key
    await load_llm_providers_to_redis()
    logger.info(f"LLM keys updated and providers reloaded: {list(updates.keys())}")
    return {
        "status": "ok",
        "configured": [k for k in _KEY_ENV_NAMES if os.environ.get(k)],
        # 前端据此提示"已校验通过"还是"未能校验,已保存"
        "verification": verdicts,
    }

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

@router.get("/profiles")
async def get_profiles(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    """
    获取角色画像列表。
    """
    profiles = db.query(RoleProfileDB).filter(RoleProfileDB.user_id == current_user.id).all()
    result = {}
    for p in profiles:
        result[p.name] = RoleProfile(
            name=p.name,
            description=p.description,
            style=p.style,
            constraints=p.constraints,
        )
    return result

@router.delete("/profiles/{name}")
async def delete_profile(
    name: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    """
    删除指定的角色画像。
    """
    profile = db.query(RoleProfileDB).filter(
        RoleProfileDB.name == name,
        RoleProfileDB.user_id == current_user.id
    ).first()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    db.delete(profile)
    db.commit()
    return {"status": "success", "message": f"Profile {name} deleted"}

@router.post("/profiles")
async def update_profile(
    profile: RoleProfile,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    """
    更新或创建角色画像。
    """
    name = profile.name
    if not name:
        raise HTTPException(status_code=400, detail="Profile name required")
    
    db_profile = db.query(RoleProfileDB).filter(
        RoleProfileDB.name == name,
        RoleProfileDB.user_id == current_user.id
    ).first()
    
    if not db_profile:
        db_profile = RoleProfileDB(name=name, user_id=current_user.id)
        db.add(db_profile)
    
    db_profile.description = profile.description
    db_profile.style = profile.style
    db_profile.constraints = profile.constraints
        
    db.commit()
    return {"status": "success"}

@router.post("/weights")
async def update_weights(weights: Dict[str, float]):
    """
    手动更新性格权重。
    """
    return {"status": "received", "weights": weights}
