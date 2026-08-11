from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.system.schema_bootstrap import init_db
from app.services.system.default_settings import load_default_settings
from app.models import RoleProfileDB, CommonSettingsDB
from app.prompts import RoleProfile, CommonSettings
import os
import json

PROVIDER_CACHE_TTL = 24 * 3600
import structlog
from app.core.cache import redis_client
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
    return str(url).strip().strip("',`\" ").rstrip(",").strip("',`\" ")


async def load_llm_providers_to_redis():
    """
    系统启动时，将 LLM 配置加载到 Redis 和内存配置管理器。

    统一 OpenAI 兼容接口：
    - 从 llm_providers.json 读取基础配置模板
    - 用环境变量覆盖 base_url / model_name / api_key
    - 用户可通过界面或 .env 自定义任意第三方服务
    """
    try:
        from app.core.paths import SERVER_DIR
        config_path = os.path.join(SERVER_DIR, "llm_providers.json")

        if not os.path.exists(config_path):
            logger.warning(f"LLM providers config file not found at {config_path}")
            return

        with open(config_path, "r", encoding="utf-8") as f:
            providers = json.load(f)

        for key, config in providers.items():
            # 从环境变量注入 API Key
            api_key_env = config.get("api_key_env")
            if api_key_env:
                env_key = os.environ.get(api_key_env)
                if env_key:
                    config["api_key"] = _normalize_api_key(env_key)

            # 从环境变量覆盖 base_url（用户自定义）
            custom_base_url = os.environ.get("OPENAI_BASE_URL")
            if custom_base_url:
                config["base_url"] = _normalize_base_url(custom_base_url)

            # 从环境变量覆盖 model_name（用户自定义）
            custom_model = os.environ.get("LLM_MODEL_NAME")
            if custom_model:
                config["model"] = custom_model.strip()

            # 1. 存入内存配置管理器
            llm_config_manager.set_provider_config(key, config)

            # 2. 存入 Redis 缓存
            redis_key = f"system:llm:provider:{key}"
            if redis_client.enabled:
                await redis_client.set(redis_key, json.dumps(config), ttl=PROVIDER_CACHE_TTL)

            logger.info(f"Loaded LLM provider config: {key}")

        # 设置默认 Provider
        default_provider = settings.DEFAULT_LLM_PROVIDER
        if default_provider:
            llm_config_manager.set_current_provider(default_provider)

        # 清除 MemoryService 缓存
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
    from app.core.paths import SERVER_DIR
    settings_path = os.path.join(SERVER_DIR, "default_settings.json")

    if not os.path.exists(settings_path):
        return

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for key, config in data.items():
            if not isinstance(config, dict):
                continue
            name = config.get("name")
            if not name:
                continue

            cache_key = f"portrait_default:{name}"
            cached = await redis_client.get(cache_key)

            if not cached:
                logger.info(f"Generating initial portrait for {name} using LLM...")
                try:
                    valid_fields = CommonSettings.model_fields.keys()
                    filtered_config = {k: v for k, v in config.items() if k in valid_fields}

                    from app.services.dialogue.generation import generate_character_portrait_async
                    from app.core.llm_config import is_any_llm_configured

                    if not is_any_llm_configured():
                        logger.info("LLM not configured yet, skipping portrait generation")
                        continue

                    portrait = await generate_character_portrait_async(
                        CommonSettings(**filtered_config),
                        session=SessionLocal(),
                    )
                    if portrait:
                        await redis_client.set(cache_key, json.dumps(portrait), ttl=3600 * 24 * 7)
                        logger.info(f"Portrait generated and cached for {name}")
                except Exception as e:
                    logger.warning(f"Failed to generate portrait for {name}: {e}")

    except Exception as e:
        logger.error(f"Failed to init portraits: {e}")


def init_personality_data(db: Session):
    """初始化人格数据。"""
    try:
        load_default_settings(db)
    except Exception as e:
        logger.error(f"Failed to init personality data: {e}")
