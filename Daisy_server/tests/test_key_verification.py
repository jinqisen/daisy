"""
保存前探活的回归。

坑:/api/config/llm_keys 原本照单全收。实测踩过 —— 一把 35 位的**搜索**密钥被填进
MAAS_API_KEY(聊天)槽位,两把密钥长度差 51 位肉眼极难发现;落盘后要等第一次对话
失败才暴露,而那时的表现是"角色卡一直生成中",用户根本联想不到是密钥填错了。

关键取舍:**只有明确的认证失败才拒绝**。超时/限流/5xx/断网一律放行 ——
否则离线或服务商抖动时用户永远配不上密钥,那比不校验更糟。
"""

import pytest

from app.services.system import key_verification as kv
from app.services.system.key_verification import INVALID, UNVERIFIED, VALID


class TestAuthFailureClassification:
    """区分"密钥不对"与"暂时不通" —— 判错方向的代价是用户被永久挡在门外。"""

    @pytest.mark.parametrize("status,body", [
        (401, "Invalid authorization header"),
        (403, "forbidden"),
        (200, '{"error":{"message":"invalid api key"}}'),
        (400, "Unauthorized"),
    ])
    def test_auth_failures_detected(self, status, body):
        assert kv._is_auth_failure(status, body) is True

    @pytest.mark.parametrize("status,body", [
        (429, "rate limit exceeded"),
        (500, "internal server error"),
        (502, "bad gateway"),
        (503, "service unavailable"),
    ])
    def test_transient_failures_not_treated_as_auth(self, status, body):
        assert kv._is_auth_failure(status, body) is False, \
            f"HTTP {status} 被判为密钥错误 —— 服务商抖动会导致正确的密钥被拒绝"


class TestVerifyKey:

    @pytest.mark.asyncio
    async def test_empty_key_rejected(self):
        status, _ = await kv.verify_key("MAAS_API_KEY", "   ")
        assert status == INVALID

    @pytest.mark.asyncio
    async def test_unknown_env_is_not_blocked(self, monkeypatch):
        """没有对应 provider 配置就无从探活,不能因此拦住用户。"""
        monkeypatch.setattr(kv, "_load_providers", lambda: {})
        status, _ = await kv.verify_key("OPENAI_API_KEY", "sk-x")
        assert status == UNVERIFIED

    @pytest.mark.asyncio
    async def test_network_error_is_not_blocked(self, monkeypatch):
        """
        核心取舍:断网时必须放行。否则用户在离线/弱网下永远无法完成首次配置。
        """
        monkeypatch.setattr(kv, "_load_providers", lambda: {
            "p": {"base_url": "https://x.invalid/v1", "model": "m", "api_key_env": "MAAS_API_KEY"}
        })

        class _Boom:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): raise OSError("network unreachable")
            async def __aexit__(self, *a): return False

        monkeypatch.setattr(kv.aiohttp, "ClientSession", _Boom)
        status, reason = await kv.verify_key("MAAS_API_KEY", "sk-x")
        assert status == UNVERIFIED, "断网导致密钥被拒 —— 用户将无法完成配置"
        assert "已按有效保存" in reason

    @pytest.mark.asyncio
    @pytest.mark.parametrize("http_status,body,expected", [
        (200, '{"choices":[]}', VALID),
        (401, "Invalid authorization header", INVALID),
        (429, "rate limited", UNVERIFIED),
        (503, "unavailable", UNVERIFIED),
    ])
    async def test_http_outcomes(self, monkeypatch, http_status, body, expected):
        monkeypatch.setattr(kv, "_load_providers", lambda: {
            "p": {"base_url": "https://api.example.com/v1", "model": "m", "api_key_env": "MAAS_API_KEY"}
        })

        class _Resp:
            status = http_status
            async def text(self): return body
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

        class _Session:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            def post(self, *a, **k): return _Resp()

        monkeypatch.setattr(kv.aiohttp, "ClientSession", _Session)
        status, _ = await kv.verify_key("MAAS_API_KEY", "sk-x")
        assert status == expected

    @pytest.mark.asyncio
    async def test_probe_is_cheap(self, monkeypatch):
        """探活只为握手,不该让模型真的生成 —— 否则每次配置都要等几十秒还烧 token。"""
        monkeypatch.setattr(kv, "_load_providers", lambda: {
            "p": {"base_url": "https://api.example.com/v1", "model": "m", "api_key_env": "MAAS_API_KEY"}
        })
        seen = {}

        class _Resp:
            status = 200
            async def text(self): return "{}"
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

        class _Session:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            def post(self, url, json=None, headers=None):
                seen["json"] = json
                seen["auth"] = (headers or {}).get("Authorization")
                return _Resp()

        monkeypatch.setattr(kv.aiohttp, "ClientSession", _Session)
        await kv.verify_key("MAAS_API_KEY", "sk-secret")
        assert seen["json"]["max_tokens"] <= 4, "探活请求不该生成长文本"
        assert seen["auth"] == "Bearer sk-secret"

    @pytest.mark.asyncio
    async def test_search_key_probes_search_endpoint(self, monkeypatch):
        """
        搜索密钥必须打搜索端点。若拿它去探聊天端点会得到 401,把一把**有效**的
        搜索密钥判成无效 —— 正是本功能要避免的那类误判的镜像。
        """
        seen = {}

        class _Resp:
            status = 200
            async def text(self): return "{}"
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

        class _Session:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            def post(self, url, json=None, headers=None):
                seen["url"] = url
                return _Resp()

        monkeypatch.setattr(kv.aiohttp, "ClientSession", _Session)
        await kv.verify_key("HUAWEI_SEARCH_API_KEY", "sk-x")
        assert "chat/completions" not in seen["url"]
        assert "search" in seen["url"]


class TestEndpointRejectsBeforePersisting:

    def test_route_probes_before_writing(self):
        """校验必须在写文件之前 —— 顺序反了等于没校验。"""
        import inspect
        from app.api.routers import config as config_router

        src = inspect.getsource(config_router.set_llm_keys)
        assert "verify_key" in src, "端点未做保存前校验"
        assert src.index("verify_key") < src.index("json.dump"), \
            "先落盘再校验 —— 错误的密钥已经写进配置文件了"

    def test_route_only_rejects_definitive_failures(self):
        import inspect
        from app.api.routers import config as config_router

        src = inspect.getsource(config_router.set_llm_keys)
        assert "INVALID" in src
        assert "UNVERIFIED" not in src.split("rejected")[1][:200], \
            "把未验证也当作拒绝 —— 断网时用户配不上密钥"
