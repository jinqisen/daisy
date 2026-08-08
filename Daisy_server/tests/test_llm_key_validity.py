"""
LLM 密钥「可用性」判定测试。

踩过的坑:配置状态原先只判断环境变量是否非空 —— 但密钥过期/被撤销后
环境变量依然有值,于是:
  configured=True → 前端不显示配置引导 → 但每次对话都 401 失败
  → 角色卡生成失败 → 用户卡在"角色卡生成中",且无处修改密钥

结论:配置状态必须反映**可用性**,而不只是**有没有填**。
"""

import pytest

from app.core import llm_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in llm_config.CHAT_KEY_ENVS:
        monkeypatch.delenv(name, raising=False)
    llm_config.clear_invalid_marks()
    yield
    llm_config.clear_invalid_marks()


class TestKeyUsability:

    def test_no_key_means_unconfigured(self):
        assert llm_config.is_any_llm_configured() is False

    def test_present_key_counts_as_configured(self, monkeypatch):
        monkeypatch.setenv("MAAS_API_KEY", "sk-something")
        assert llm_config.is_any_llm_configured() is True

    def test_invalidated_key_no_longer_counts(self, monkeypatch):
        """
        核心回归:认证失败后必须视为未配置,好让前端重新引导用户填写。
        """
        monkeypatch.setenv("MAAS_API_KEY", "expired-key")
        assert llm_config.is_any_llm_configured() is True
        llm_config.mark_key_invalid("MAAS_API_KEY")
        assert llm_config.is_any_llm_configured() is False, \
            "失效密钥仍被当作已配置 —— 用户会卡在角色卡生成中且无处可改"

    def test_other_valid_key_still_counts(self, monkeypatch):
        """一个密钥失效不应影响另一个可用的。"""
        monkeypatch.setenv("MAAS_API_KEY", "expired")
        monkeypatch.setenv("SILICONFLOW_API_KEY", "good")
        llm_config.mark_key_invalid("MAAS_API_KEY")
        assert llm_config.is_any_llm_configured() is True

    def test_refill_clears_invalid_mark(self, monkeypatch):
        """用户重填密钥后应给新密钥机会,否则新密钥也被旧记录连累。"""
        monkeypatch.setenv("MAAS_API_KEY", "expired")
        llm_config.mark_key_invalid("MAAS_API_KEY")
        assert llm_config.is_any_llm_configured() is False
        llm_config.clear_invalid_marks()
        assert llm_config.is_any_llm_configured() is True

    def test_status_exposes_invalid_flag(self, monkeypatch):
        """前端据此把提示从"请配置"改为"密钥已失效,请更新"。"""
        monkeypatch.setenv("MAAS_API_KEY", "expired")
        assert llm_config.llm_config_status()["has_invalid_key"] is False
        llm_config.mark_key_invalid("MAAS_API_KEY")
        st = llm_config.llm_config_status()
        assert st["has_invalid_key"] is True
        assert "MAAS_API_KEY" in st["invalid_keys"]

    def test_status_never_leaks_key_material(self, monkeypatch):
        """状态接口不得回传密钥明文。"""
        monkeypatch.setenv("MAAS_API_KEY", "super-secret-value")
        assert "super-secret-value" not in str(llm_config.llm_config_status())


class TestAuthErrorDetection:
    """只有认证类错误才标记密钥失效 —— 超时/限流不应误伤。"""

    def _mark(self, exc):
        from app.core.llm import LLMService
        llm_config.clear_invalid_marks()
        LLMService._mark_key_invalid_if_auth_error(exc, {"provider": "huaweicloud"})
        return "MAAS_API_KEY" in llm_config._INVALIDATED_KEYS

    @pytest.mark.parametrize("msg", [
        "Error code: 401 - Invalid authorization header",
        "Unauthorized",
        "invalid api key provided",
    ])
    def test_auth_errors_mark_invalid(self, msg):
        assert self._mark(Exception(msg)) is True

    @pytest.mark.parametrize("msg", [
        "Request timed out.",
        "Error code: 429 - rate limit exceeded",
        "Connection error.",
        "Error code: 500 - internal server error",
    ])
    def test_transient_errors_do_not_mark_invalid(self, msg):
        assert self._mark(Exception(msg)) is False, \
            f"瞬时故障被误判为密钥失效会让用户被要求重填正确的密钥: {msg}"
