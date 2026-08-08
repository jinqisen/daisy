"""
Qwen3 thinking 关闭测试。

背景:qwen3-32b 默认生成大量不可见的 reasoning_content(实测占 45% completion_tokens),
关闭后提速 27-48%,而 prompt 中显式要求的 CoT 保留在可见输出中。

锁定三件事:
1. qwen3 模型注入 enable_thinking=false;
2. 非 qwen3 模型(deepseek 等)不受影响 —— 它们没有该模板参数,误传可能报错;
3. 缓存键区分 thinking 开关,避免配置变更后复用旧实例。
"""

import pytest

from app.core.config import settings
from app.core.llm import LLMService


@pytest.fixture
def svc():
    s = LLMService()
    s._llm_cache = {}  # 隔离缓存,避免跨用例污染
    return s


def _extra_body(llm):
    return getattr(llm, "extra_body", None)


def test_qwen3_gets_thinking_disabled(svc, monkeypatch):
    monkeypatch.setattr(settings, "DISABLE_QWEN_THINKING", True)
    llm = svc.get_llm(api_key="sk-testkey123456", base_url="http://x/v1", model="qwen3-32b")
    assert _extra_body(llm) == {"chat_template_kwargs": {"enable_thinking": False}}


def test_non_qwen_model_untouched(svc, monkeypatch):
    """deepseek 等模型不支持该模板参数,必须不注入。"""
    monkeypatch.setattr(settings, "DISABLE_QWEN_THINKING", True)
    llm = svc.get_llm(api_key="sk-testkey123456", base_url="http://x/v1", model="deepseek-v3.2")
    assert not _extra_body(llm)


def test_switch_off_restores_default(svc, monkeypatch):
    monkeypatch.setattr(settings, "DISABLE_QWEN_THINKING", False)
    llm = svc.get_llm(api_key="sk-testkey123456", base_url="http://x/v1", model="qwen3-32b")
    assert not _extra_body(llm)


def test_cache_key_separates_thinking_variants(svc, monkeypatch):
    """开关切换后不得复用旧实例,否则配置改了却不生效。"""
    monkeypatch.setattr(settings, "DISABLE_QWEN_THINKING", True)
    on = svc.get_llm(api_key="sk-testkey123456", base_url="http://x/v1", model="qwen3-32b")
    monkeypatch.setattr(settings, "DISABLE_QWEN_THINKING", False)
    off = svc.get_llm(api_key="sk-testkey123456", base_url="http://x/v1", model="qwen3-32b")
    assert on is not off
    assert _extra_body(on) and not _extra_body(off)
