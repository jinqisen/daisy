"""
记忆系统 feature 测试(三层记忆中的语义层)。

重点锁定 mem0 embedding 的 `dimensions` 参数问题:
mem0 的 OpenAIEmbedding.embed() 无条件发送 `dimensions`,而该参数仅 OpenAI
text-embedding-3-* 支持;SiliconFlow 的 BAAI/bge-m3 收到后直接 400(code 20015)。
add 与 search 共用 embed(),故长期记忆曾完全不工作(日志中出现 136 次)。

这里用 fake client 验证补丁行为,不依赖网络。
"""

from types import SimpleNamespace

import pytest


class _FakeEmbeddings:
    def __init__(self, sink):
        self._sink = sink

    def create(self, **kwargs):
        self._sink.update(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.0] * 1024)])


class _FakeClient:
    def __init__(self, base_url, sink):
        self.base_url = base_url
        self.embeddings = _FakeEmbeddings(sink)


def _embed_with(base_url: str):
    """用指定 base_url 调用打过补丁的 embed(),返回实际发出的请求参数。"""
    import app.services.memory.store  # noqa: F401  确保 monkeypatch 已应用
    from mem0.embeddings.openai import OpenAIEmbedding

    sink = {}
    obj = OpenAIEmbedding.__new__(OpenAIEmbedding)
    obj.client = _FakeClient(base_url, sink)
    obj.config = SimpleNamespace(model="BAAI/bge-m3", embedding_dims=1024)
    OpenAIEmbedding.embed(obj, "测试文本")
    return sink


def test_dimensions_not_sent_to_siliconflow():
    """
    对非 OpenAI 端点不得发送 dimensions —— 这是长期记忆失效的根因。
    """
    sent = _embed_with("https://api.siliconflow.cn/v1")
    assert "dimensions" not in sent, (
        "向 SiliconFlow 发送了 dimensions 参数,会触发 400 code 20015,长期记忆将完全失效"
    )
    assert sent["model"] == "BAAI/bge-m3"
    assert sent["input"] == ["测试文本"]


def test_dimensions_still_sent_to_official_openai():
    """官方 OpenAI 支持该参数,不应误伤。"""
    sent = _embed_with("https://api.openai.com/v1")
    assert sent.get("dimensions") == 1024


def test_newlines_normalized():
    """embed 前应把换行替换为空格(mem0 原实现的行为,补丁需保留)。"""
    sent = _embed_with("https://api.siliconflow.cn/v1")
    assert "\n" not in sent["input"][0]


def test_patch_applied_at_import():
    """
    补丁必须在 import app.services.memory.store 时生效。
    若 mem0 升级后函数签名变化导致补丁未挂上,此测试会失败。
    """
    import app.services.memory.store  # noqa: F401
    from mem0.embeddings.openai import OpenAIEmbedding

    assert OpenAIEmbedding.embed.__name__ == "_embed_without_invalid_dimensions", (
        "mem0 embed 补丁未生效 —— 长期记忆会因 dimensions 参数而 400"
    )
