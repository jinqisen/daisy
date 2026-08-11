"""
LLM 配置管理 —— 统一 OpenAI 兼容接口。

设计原则：
- 用户只需配置一个 Base URL + API Key + 模型名，适配所有 OpenAI 兼容服务商
- 不写死任何特定服务商（华为云、硅基流动等）
- 桌面版 keyless 分发：包内不含任何 API Key，用户首次运行自行填入
"""

import threading
from typing import Dict, Optional, Any
import os
import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# 统一的环境变量名
# ---------------------------------------------------------------------------
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_BASE_URL_ENV = "OPENAI_BASE_URL"
LLM_MODEL_NAME_ENV = "LLM_MODEL_NAME"

# 对话主链路可用的密钥
CHAT_KEY_ENVS = [OPENAI_API_KEY_ENV]


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
        """已加载的 provider 名称。"""
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
# LLM 配置状态判定
# ---------------------------------------------------------------------------

# 已被服务端判定为无效的密钥（认证失败）
_INVALIDATED_KEYS: set = set()


def _has_env(name: Optional[str]) -> bool:
    if not name:
        return False
    value = os.environ.get(name)
    return bool(value and value.strip())


def mark_key_invalid(env_name: str) -> None:
    if env_name:
        _INVALIDATED_KEYS.add(env_name)
        logger.warning(f"LLM key marked invalid (authentication failed): {env_name}")


def clear_invalid_marks() -> None:
    """用户重新填写密钥后调用，给新密钥一次机会。"""
    _INVALIDATED_KEYS.clear()


def is_key_usable(env_name: str) -> bool:
    return _has_env(env_name) and env_name not in _INVALIDATED_KEYS


def is_any_llm_configured() -> bool:
    """
    是否至少有一个可用的 LLM 密钥。
    """
    return any(is_key_usable(name) for name in CHAT_KEY_ENVS)


def llm_config_status() -> Dict[str, Any]:
    """给前端的配置状态摘要（不含任何密钥明文）。"""
    invalid = sorted(_INVALIDATED_KEYS)
    return {
        "configured": is_any_llm_configured(),
        "keys": {name: _has_env(name) for name in CHAT_KEY_ENVS},
        "invalid_keys": invalid,
        "has_invalid_key": bool(invalid),
        # 返回当前配置的 base_url 和 model_name（不含密钥）
        "base_url": os.environ.get(OPENAI_BASE_URL_ENV, ""),
        "model_name": os.environ.get(LLM_MODEL_NAME_ENV, ""),
    }
