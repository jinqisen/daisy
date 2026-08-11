"""
LLM 配置 API 端点 —— 统一 OpenAI 兼容接口。

用户配置：Base URL + API Key + 模型名，适配所有 OpenAI 兼容服务商。
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
import json
import os
import structlog

from app.core.database import get_db
from app.core.config import settings
from app.core.cache import redis_client
from app.models import UserDB
from app.api.deps import get_current_user

logger = structlog.get_logger()
router = APIRouter()

# 统一密钥环境变量名
_KEY_ENV_NAMES = ["OPENAI_API_KEY", "OPENAI_BASE_URL", "LLM_MODEL_NAME", "HUAWEI_SEARCH_API_KEY"]


def _user_config_path() -> str:
    """密钥持久化目标：优先 DAISY_CONFIG_PATH（桌面版指向用户目录），否则源码树。"""
    p = os.environ.get("DAISY_CONFIG_PATH")
    if p:
        return p
    from app.core.paths import SERVER_DIR
    return os.path.join(SERVER_DIR, "server_config.json")


@router.get("/providers")
async def get_llm_providers():
    """
    返回当前 LLM 配置状态（base_url + model_name + 密钥是否已配置）。
    不再返回服务商列表 —— 用户自行输入。
    """
    from app.core.llm_config import llm_config_status, OPENAI_API_KEY_ENV, OPENAI_BASE_URL_ENV, LLM_MODEL_NAME_ENV

    status = llm_config_status()
    return {
        "configured": status["configured"],
        "has_invalid_key": status["has_invalid_key"],
        "invalid_keys": status["invalid_keys"],
        "base_url": os.environ.get(OPENAI_BASE_URL_ENV, ""),
        "model_name": os.environ.get(LLM_MODEL_NAME_ENV, ""),
        "has_api_key": bool(os.environ.get(OPENAI_API_KEY_ENV)),
    }


@router.get("/llm_keys")
async def get_llm_keys(current_user: UserDB = Depends(get_current_user)):
    """返回各密钥是否已配置（不回传明文）。"""
    return {name: bool(os.environ.get(name)) for name in _KEY_ENV_NAMES}


@router.get("/llm_status")
async def get_llm_status(current_user: UserDB = Depends(get_current_user)):
    """
    LLM 配置状态摘要（不含密钥明文）。
    """
    from app.core.llm_config import llm_config_status
    return llm_config_status()


@router.post("/llm_keys")
async def set_llm_keys(payload: Dict[str, str], current_user: UserDB = Depends(get_current_user)):
    """
    设置 LLM 配置。

    接收字段：
    - OPENAI_API_KEY: API 密钥
    - OPENAI_BASE_URL: 接口地址（如 https://api.openai.com/v1）
    - LLM_MODEL_NAME: 模型名称（如 gpt-4o、deepseek-v3.2）
    - HUAWEI_SEARCH_API_KEY: 联网搜索密钥（可选）

    保存前探活验证，只有明确认证失败才拒绝。
    """
    from app.services.system.init_data import load_llm_providers_to_redis
    from app.services.system.key_verification import verify_key, VALID, INVALID

    # 允许的字段
    allowed_keys = {"OPENAI_API_KEY", "OPENAI_BASE_URL", "LLM_MODEL_NAME", "HUAWEI_SEARCH_API_KEY"}

    updates = {k: v for k, v in payload.items() if k in allowed_keys and isinstance(v, str) and v.strip()}
    if not updates:
        raise HTTPException(status_code=400, detail="未提供有效的配置项")

    verdicts = {}

    # 验证 API Key（如果有）
    api_key = updates.get("OPENAI_API_KEY")
    if api_key:
        # 验证时传递用户提供的 base_url 和 model_name
        base_url = updates.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or ""
        model_name = updates.get("LLM_MODEL_NAME") or os.environ.get("LLM_MODEL_NAME") or "gpt-4o"
        status, reason = await verify_key("OPENAI_API_KEY", api_key, base_url, model_name)
        verdicts["OPENAI_API_KEY"] = {"status": status, "reason": reason}
        logger.info(f"Key probe OPENAI_API_KEY: {status} ({reason})")

        rejected = {k: v["reason"] for k, v in verdicts.items() if v["status"] == INVALID}
        if rejected:
            detail = "；".join(f"{k}: {r}" for k, r in rejected.items())
            raise HTTPException(status_code=400, detail=detail)

    # 验证搜索密钥（如果有）
    search_key = updates.get("HUAWEI_SEARCH_API_KEY")
    if search_key:
        status, reason = await verify_key("HUAWEI_SEARCH_API_KEY", search_key, "", "")
        verdicts["HUAWEI_SEARCH_API_KEY"] = {"status": status, "reason": reason}
        if status == INVALID:
            raise HTTPException(status_code=400, detail=f"HUAWEI_SEARCH_API_KEY: {reason}")

    # 1. 注入进程环境
    for k, v in updates.items():
        os.environ[k] = v.strip()

    # 2. 同步更新 settings 单例
    for k, v in updates.items():
        if hasattr(settings, k):
            try:
                setattr(settings, k, v.strip())
            except Exception as e:
                logger.warning(f"Failed to sync {k} into settings: {e}")

    # 同步 OPENAI_BASE_URL 和 LLM_MODEL_NAME
    if "OPENAI_BASE_URL" in updates:
        try:
            settings.OPENAI_BASE_URL = updates["OPENAI_BASE_URL"].strip()
        except Exception:
            pass
    if "LLM_MODEL_NAME" in updates:
        try:
            settings.LLM_MODEL_NAME = updates["LLM_MODEL_NAME"].strip()
        except Exception:
            pass

    # 3. 持久化到用户配置文件
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

    # 4. 清除密钥失效标记
    from app.core.llm_config import clear_invalid_marks
    clear_invalid_marks()

    # 5. 热重载 provider
    await load_llm_providers_to_redis()
    logger.info(f"LLM config updated: {list(updates.keys())}")
    return {
        "status": "ok",
        "configured": [k for k in _KEY_ENV_NAMES if os.environ.get(k)],
        "verification": verdicts,
    }
