import threading
from typing import Dict, Optional, Any
import structlog

logger = structlog.get_logger()

class LLMConfigManager:
    """
    Thread-safe singleton for managing in-memory LLM configurations.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._current_provider: Optional[str] = None
        self._providers: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = LLMConfigManager()
        return cls._instance

    def set_provider_config(self, provider_name: str, config: Dict[str, Any]):
        with self._lock:
            self._providers[provider_name] = config
            logger.info(f"Loaded config for provider: {provider_name}")

    def get_provider_config(self, provider_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._providers.get(provider_name)

    def list_providers(self) -> list:
        """已加载的 provider 名称。供需要"任选一个可用服务商"的场景使用(如记忆抽取回落)。"""
        with self._lock:
            return list(self._providers.keys())

    def set_current_provider(self, provider_name: str):
        with self._lock:
            self._current_provider = provider_name
            logger.info(f"Set current LLM provider to: {provider_name}")

    def get_current_provider(self) -> Optional[str]:
        with self._lock:
            return self._current_provider

# Global instance
llm_config_manager = LLMConfigManager.get_instance()


# ---------------------------------------------------------------------------
# LLM 配置状态判定(单一事实来源)
#
# 桌面版为 keyless 分发:包内不含任何 API Key,用户首次运行需自行填入。
# 「是否已配置 LLM」被多处使用(角色卡兜底策略、前端配置引导门禁),集中在此
# 避免各处口径不一致。
# ---------------------------------------------------------------------------

import os

# provider → 密钥环境变量名(与 llm_providers.json 的 api_key_env 一致)
PROVIDER_KEY_ENVS: Dict[str, str] = {
    "huaweicloud": "MAAS_API_KEY",
    "siliconflow": "SILICONFLOW_API_KEY",
    "openai": "OPENAI_API_KEY",
}

# 对话主链路可用的密钥(用于判断"能否开始对话")
CHAT_KEY_ENVS = ["MAAS_API_KEY", "SILICONFLOW_API_KEY", "OPENAI_API_KEY"]


def _has_env(name: Optional[str]) -> bool:
    if not name:
        return False
    value = os.environ.get(name)
    return bool(value and value.strip())


# 已被服务端判定为无效的密钥(认证失败)。
# 「填了值」不等于「能用」:密钥过期/被撤销时环境变量依然非空,若仅凭非空判定
# 已配置,前端就不会显示配置引导,而对话又必然 401 失败 —— 用户会卡在
# "角色卡生成中" 且无处可改。这里记录认证失败,使配置状态反映真实可用性。
_INVALIDATED_KEYS: set = set()


def mark_key_invalid(env_name: str) -> None:
    if env_name:
        _INVALIDATED_KEYS.add(env_name)
        logger.warning(f"LLM key marked invalid (authentication failed): {env_name}")


def clear_invalid_marks() -> None:
    """用户重新填写密钥后调用,给新密钥一次机会。"""
    _INVALIDATED_KEYS.clear()


def is_key_usable(env_name: str) -> bool:
    return _has_env(env_name) and env_name not in _INVALIDATED_KEYS


def is_any_llm_configured() -> bool:
    """
    是否至少有一个**可用**的 LLM 密钥。

    注意语义:这里判断的是"可用",不只是"有值"。已被认证失败标记的密钥
    视为未配置,以便前端重新引导用户填写。
    """
    return any(is_key_usable(name) for name in CHAT_KEY_ENVS)


def is_provider_configured(provider: str) -> bool:
    return is_key_usable(PROVIDER_KEY_ENVS.get(provider) or "")


def llm_config_status() -> Dict[str, Any]:
    """给前端的配置状态摘要(不含任何密钥明文)。"""
    invalid = sorted(_INVALIDATED_KEYS)
    return {
        "configured": is_any_llm_configured(),
        "providers": {p: is_provider_configured(p) for p in PROVIDER_KEY_ENVS},
        "keys": {name: _has_env(name) for name in CHAT_KEY_ENVS},
        # 已填但认证失败的密钥 —— 前端据此提示"密钥无效,请重新填写",
        # 而不是让用户对着"角色卡生成中"干等
        "invalid_keys": invalid,
        "has_invalid_key": bool(invalid),
        "key_env_by_provider": PROVIDER_KEY_ENVS,
    }
