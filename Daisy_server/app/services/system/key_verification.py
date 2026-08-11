"""
保存前校验 API Key —— 统一 OpenAI 兼容接口。

用户提供 base_url + api_key + model_name，直接打 /v1/chat/completions 探活。
只有明确的认证失败才拒绝；超时/限流/5xx/断网一律放行。
"""

import json
import os
from typing import Optional, Tuple

import aiohttp
import structlog

from app.core.config import settings

logger = structlog.get_logger()

_PROBE_TIMEOUT_SEC = 20

VALID = "valid"
INVALID = "invalid"
UNVERIFIED = "unverified"


def _is_auth_failure(status: int, body: str) -> bool:
    """区分'密钥不对'与'暂时不通'。"""
    if status in (401, 403):
        return True
    lowered = (body or "").lower()
    return any(k in lowered for k in (
        "invalid authorization", "invalid api key", "unauthorized",
        "invalid_api_key", "authentication",
    ))


async def verify_key(env_name: str, key: str, base_url: str = "", model_name: str = "") -> Tuple[str, str]:
    """
    返回 (状态, 说明)。状态取 VALID / INVALID / UNVERIFIED。

    参数：
    - env_name: 环境变量名（OPENAI_API_KEY 或 HUAWEI_SEARCH_API_KEY）
    - key: 密钥值
    - base_url: 用户提供的 API 地址（仅 OPENAI_API_KEY 时使用）
    - model_name: 用户提供的模型名（仅 OPENAI_API_KEY 时使用）
    """
    key = (key or "").strip()
    if not key:
        return INVALID, "密钥为空"

    if env_name == "HUAWEI_SEARCH_API_KEY":
        url = settings.HUAWEI_SEARCH_ENDPOINT or \
            "https://cbs-ext.cn-southwest-2.myhuaweicloud.com/v1/ai-tools/web-search"
        payload = {"query": "test", "freshness": "noLimit", "count": 1}
    else:
        # 统一 OpenAI 兼容接口探活
        url_base = (base_url or "").strip().rstrip("/")
        if not url_base:
            # 如果用户没提供 base_url，尝试从环境变量取，再不行用默认值
            url_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")

        model = (model_name or "").strip() or os.environ.get("LLM_MODEL_NAME", "gpt-4o").strip()
        url = f"{url_base}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        timeout = aiohttp.ClientTimeout(total=_PROBE_TIMEOUT_SEC)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                body = await resp.text()
                if resp.status == 200:
                    return VALID, "校验通过"
                if _is_auth_failure(resp.status, body):
                    return INVALID, "服务商拒绝了这个密钥（可能填错了服务，或已失效）"
                return UNVERIFIED, f"未能完成校验（HTTP {resp.status}），已按有效保存"
    except Exception as e:
        return UNVERIFIED, f"网络不可达，未能校验（{type(e).__name__}），已按有效保存"
