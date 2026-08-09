"""
LLM 服务商与密钥的配置接口。

从原来的 config.py(431 行、11 个端点、三类关注点)拆出。
三类东西唯一的共同点只是都挂在 /config 前缀下 —— 那是 URL 结构,不是内聚性。

**URL 路径保持不变**:三个 router 仍以同一前缀挂载,前端无需改动。
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

@router.get("/providers")
async def get_llm_providers():
    """
    获取可用的 LLM 提供商列表。
    """
    # app/api/routers/config.py -> app/api/routers -> app/api -> app -> Daisy_server
    from app.core.paths import SERVER_DIR
    base_dir = SERVER_DIR
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
    from app.core.paths import SERVER_DIR
    base_dir = SERVER_DIR
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
