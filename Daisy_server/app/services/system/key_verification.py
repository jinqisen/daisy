"""
保存前校验 API Key。

为什么需要:/api/config/llm_keys 原本照单全收,填错服务的密钥也会落盘,
要等第一次对话失败才暴露 —— 而那时的表现是"角色卡一直生成中",用户根本
联想不到是密钥填错了槽位。实测踩过:一把 35 位的**搜索**密钥被填进
MAAS_API_KEY(聊天)槽位,两把密钥长度差 51 位,肉眼极难发现装错。

关键取舍:**只有明确的认证失败才拒绝**。超时、限流、5xx、连不上网一律放行 ——
否则断网或服务商抖动时用户就永远配不上密钥,那比不校验还糟。
"""

import json
import os
from typing import Optional, Tuple

import aiohttp
import structlog

from app.core.config import settings, resolve_bundled_asset

logger = structlog.get_logger()

# 探活超时:只是要一个 token,给足握手时间即可,不必等模型真的想完
_PROBE_TIMEOUT_SEC = 20

VALID = "valid"
INVALID = "invalid"          # 明确认证失败 → 拒绝落盘
UNVERIFIED = "unverified"    # 网络/限流/服务端问题 → 放行,但告知未验证


def _load_providers() -> dict:
    # 走统一解析:配置里的路径相对 cwd,冻结环境下要落到解包目录(见 resolve_bundled_asset)
    path = resolve_bundled_asset("./Daisy_server/llm_providers.json")
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"无法读取 llm_providers.json: {e}")
        return {}


def _provider_for_env(env_name: str) -> Optional[dict]:
    for cfg in _load_providers().values():
        if cfg.get("api_key_env") == env_name:
            return cfg
    return None


def _is_auth_failure(status: int, body: str) -> bool:
    """
    区分"密钥不对"与"暂时不通"。
    401/403 是标准答案;部分网关把鉴权错误塞在 200/400 的 body 里,故再看文本。
    """
    if status in (401, 403):
        return True
    lowered = (body or "").lower()
    return any(k in lowered for k in (
        "invalid authorization", "invalid api key", "unauthorized",
        "invalid_api_key", "authentication",
    ))


async def verify_key(env_name: str, key: str) -> Tuple[str, str]:
    """
    返回 (状态, 说明)。状态取 VALID / INVALID / UNVERIFIED。
    """
    key = (key or "").strip()
    if not key:
        return INVALID, "密钥为空"

    if env_name == "HUAWEI_SEARCH_API_KEY":
        url = settings.HUAWEI_SEARCH_ENDPOINT or \
            "https://cbs-ext.cn-southwest-2.myhuaweicloud.com/v1/ai-tools/web-search"
        payload = {"query": "test", "freshness": "noLimit", "count": 1}
    else:
        provider = _provider_for_env(env_name)
        if not provider:
            # 没有对应 provider 配置就无从探活,不能因此拦住用户
            return UNVERIFIED, "未找到该密钥对应的服务商配置,已跳过校验"
        url = f"{provider['base_url'].rstrip('/')}/chat/completions"
        payload = {
            "model": provider.get("model"),
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
                    return INVALID, "服务商拒绝了这个密钥(可能填错了服务,或已失效)"
                # 429 / 5xx / 其他:不是密钥的问题,放行
                return UNVERIFIED, f"未能完成校验(HTTP {resp.status}),已按有效保存"
    except Exception as e:
        # 超时、DNS、断网 —— 一律放行,否则离线场景永远配不上
        return UNVERIFIED, f"网络不可达,未能校验({type(e).__name__}),已按有效保存"
