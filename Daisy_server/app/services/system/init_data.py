from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.system.schema_bootstrap import init_db
from app.core.config import load_default_settings
from app.models import RoleProfileDB, CommonSettingsDB
from app.prompts import RoleProfile, CommonSettings
import os
import json
import structlog
from app.core.redis import redis_client
from app.core.llm_config import llm_config_manager
from app.core.config import settings

logger = structlog.get_logger()


def _normalize_api_key(api_key: str | None) -> str | None:
    if api_key is None:
        return None
    key = str(api_key).strip()
    if not key:
        return ""

    if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()

    lower = key.lower()
    if lower.startswith("authorization:"):
        key = key.split(":", 1)[1].strip()
        lower = key.lower()

    if lower.startswith("bearer "):
        key = key[7:].strip()

    return key

def _normalize_base_url(url: str | None) -> str | None:
    if not url:
        return url
    
    # 移除常见的包裹字符和末尾逗号
    return str(url).strip().strip("',`\" ").rstrip(",").strip("',`\" ")

async def load_llm_providers_to_redis():
    """
    系统启动时，将 LLM 配置（含环境变量中的 Key）加载到 Redis 和内存配置管理器。
    """
    try:
        # 修改：从根目录加载 llm_providers.json
        # 向上回退到项目根目录 (app/core -> app -> Daisy_server)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(base_dir, "llm_providers.json")
        
        if not os.path.exists(config_path):
            logger.warning(f"LLM providers config file not found at {config_path}")
            return

        with open(config_path, "r", encoding="utf-8") as f:
            providers = json.load(f)

        for key, config in providers.items():
            # 尝试从环境变量注入 API Key
            api_key_env = config.get("api_key_env")
            if api_key_env:
                env_key = os.environ.get(api_key_env)
                if env_key:
                    # 将解析后的 Key 注入到配置中，方便后续直接使用
                    # 注意：虽然我们在 Redis 中存储了 Key，但要确保 Redis 实例安全
                    config["api_key"] = _normalize_api_key(env_key)
            
            # 1. 存入内存配置管理器 (同步/线程安全)
            llm_config_manager.set_provider_config(key, config)

            # 2. 构建 Redis Key 并存入 Redis
            redis_key = f"system:llm:provider:{key}"
            if redis_client.enabled:
                await redis_client.set(redis_key, json.dumps(config), ttl=None) # 不过期
            
            logger.info(f"Loaded LLM provider config: {key}")

        # 设置默认 Provider
        default_provider = settings.DEFAULT_LLM_PROVIDER
        if default_provider:
            llm_config_manager.set_current_provider(default_provider)
            if redis_client.enabled:
                await redis_client.set("system:llm:current_provider", default_provider)
            
        # 让依赖 provider 的缓存实例失效。
        # MemoryService 由 @lru_cache 构造,provider 在首次构造时就定死了 ——
        # 用户后来补配密钥或换了服务商,它仍抱着旧配置(或仍是构造失败的状态),
        # 直到重启才恢复。热重载既然发生了,这里必须一并清掉。
        try:
            from app.services.memory.store import get_memory_service
            get_memory_service.cache_clear()
            logger.info("MemoryService cache cleared; will rebuild with current provider.")
        except Exception as e:
            logger.warning(f"Failed to clear MemoryService cache: {e}")

    except Exception as e:
        logger.error(f"Failed to load LLM providers: {e}")

async def init_portraits():
    """
    检查并缓存预设角色的画像。
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    settings_path = os.path.join(base_dir, "default_settings.json")
    
    if not os.path.exists(settings_path):
        return

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        for key, config in data.items():
            if not isinstance(config, dict): continue
            name = config.get("name")
            if not name: continue
            
            # Check Redis (Use a specific key for default portraits)
            cache_key = f"portrait_default:{name}"
            
            # TODO: Remove this force-clear after verification
            # Force clear cache to verify LLM generation on startup
            # if redis_client.enabled:
            #     await redis_client.delete(cache_key)
            #     logger.info(f"Force cleared cache for {name} to verify LLM generation.")

            cached = await redis_client.get(cache_key)
            
            if not cached:
                logger.info(f"Generating initial portrait for {name} using LLM...")
                try:
                    # Filter config to match CommonSettings fields
                    valid_fields = CommonSettings.model_fields.keys()
                    filtered_config = {k: v for k, v in config.items() if k in valid_fields}
                    
                    settings_obj = CommonSettings(**filtered_config)
                    
                    # Import here to avoid circular imports if any
                    from app.services.dialogue.generation import generate_character_portrait_async
                    
                    # Generate
                    start_time = os.times()
                    portrait = await generate_character_portrait_async("system_init", settings_obj)
                    
                    if portrait:
                        logger.info(f"Successfully generated portrait for {name}. Length: {len(portrait)}")
                        # Cache indefinitely
                        await redis_client.set(cache_key, portrait, ttl=86400 * 30)
                        logger.info(f"Portrait for {name} cached.")
                    else:
                        logger.warning(f"Generated portrait for {name} is empty.")
                except Exception as e:
                    logger.error(f"Failed to generate portrait for {name}: {e}")
            else:
                logger.info(f"Portrait for {name} already cached. Skipping LLM generation.")
                
    except Exception as e:
        logger.error(f"Error in init_portraits: {e}")

# New profiles based on Zhihu article: 6 Love Styles
# Note: Gender, Age, Occupation, Backstory, World Setting are now in CommonSettings
INITIAL_PROFILES = [
    RoleProfile(
        name="Eros", # 爱欲型
        description="浪漫、热情、关注外表吸引力。相信一见钟情，追求强烈的化学反应。性爱热烈且令人满足。",
        style=["热情", "浪漫", "直白", "赞美"],
        constraints=["表达强烈的爱意", "关注对方的外表和魅力", "强调一见钟情的感觉"]
    ),
    RoleProfile(
        name="Ludus", # 游戏型
        description="把恋爱当作游戏，追求乐趣和刺激。不愿给承诺，喜欢保持神秘和距离感。可能同时与多人交往，视爱与性为“战利品”。",
        style=["幽默", "调情", "玩世不恭", "神秘"],
        constraints=["避免做出长期承诺", "保持轻松愉快的对话氛围", "将关系视为游戏"]
    ),
    RoleProfile(
        name="Storge", # 友伴型
        description="慢热、基于友谊的爱。追求安稳、信任和舒适。从朋友发展为恋人，维持深刻、长期的友谊。从肢体接触中获得快乐。",
        style=["温和", "支持", "耐心", "可靠"],
        constraints=["提供稳定的情感支持", "强调信任和陪伴", "表现出像老朋友一样的关心"]
    ),
    RoleProfile(
        name="Pragma", # 现实型
        description="理性、冷静、务实。考虑现实条件（家庭、能力、职业帮助）。敦促伴侣努力向上，若符合要求则保持承诺。",
        style=["理智", "客观", "建议", "规划"],
        constraints=["提供实际的建议", "关注长期规划和价值", "基于现实条件评估关系"]
    ),
    RoleProfile(
        name="Mania", # 狂热型
        description="情绪化、占有欲强、依赖性强。喜怒无常，完全以对方为中心。有强烈的占有欲和嫉妒心，无法专心做别的事。",
        style=["情绪化", "激烈", "依赖", "疑问"],
        constraints=["表现出强烈的依赖和不安全感", "对用户的关注极其敏感", "表现出嫉妒和占有欲"]
    ),
    RoleProfile(
        name="Agape", # 奉献型
        description="无私、利他、奉献。愿意牺牲自己满足对方。把爱视为一种责任。在对方困难时全力相助，不求回报。",
        style=["无私", "关怀", "顺从", "温暖"],
        constraints=["优先满足用户需求", "即使牺牲自己也不抱怨", "视爱为责任和付出"]
    )
]

def init_personality_data(db: Session):
    # 如果不存在，初始化通用设置
    if not db.query(CommonSettingsDB).first():
        default_settings = load_default_settings()
        common = CommonSettingsDB(
            id=1,
            **default_settings
        )
        db.add(common)

    # 初始化角色配置
    existing_profiles = {p.name for p in db.query(RoleProfileDB).all()}
    for profile in INITIAL_PROFILES:
        if profile.name not in existing_profiles:
            db_obj = RoleProfileDB(**profile.model_dump())
            db.add(db_obj)
    
    db.commit()
