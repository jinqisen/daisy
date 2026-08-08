import json
import os
import sys
from types import SimpleNamespace

import pytest


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.workflow.graph as graph_module
import app.workflow.nodes.fast_path as fast_path_module
import app.workflow.nodes.memory as memory_module

from app.agents.daisy.config import CommonSettings
from app.core.smart_cache import _l1_cache


@pytest.mark.asyncio
async def test_route_cache_is_scoped_by_session(monkeypatch):
    calls: list[str] = []

    async def fake_route(state):
        calls.append(state["session_id"])
        return "DEEP"

    monkeypatch.setattr(graph_module.router, "route", fake_route)
    _l1_cache.clear()

    base_state = {"user_id": 7, "user_input": "讲个故事吧"}

    assert await graph_module.route_logic({**base_state, "session_id": "session-a"}) == "DEEP"
    assert await graph_module.route_logic({**base_state, "session_id": "session-b"}) == "DEEP"
    assert await graph_module.route_logic({**base_state, "session_id": "session-a"}) == "DEEP"

    assert calls == ["session-a", "session-b"]


@pytest.mark.asyncio
async def test_standard_path_uses_session_context_and_cached_summary(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_get_common_settings_async(_user_id):
        return CommonSettings(name="Daisy", core_system_prompt="core")

    class FakeMemoryService:
        def search_memory(self, *_args, **_kwargs):
            return ["一起看过海边日落"]

    class FakeLLMService:
        def get_standard_llm(self):
            return object()

        async def generate_response_async(self, **kwargs):
            captured["context"] = kwargs["context"]
            captured["system_prompt"] = kwargs["system_prompt"]
            return "好的，我记得。"

    async def fake_add_trace(_state, _node_id, input_data, output_data):
        captured["trace_input"] = input_data
        return {"standard_generate": {"input": input_data, "output": output_data}}

    async def fake_get_cached_session_summary(session_id):
        assert session_id == "session-a"
        return "这是 session-a 的摘要缓存", 12

    def fake_get_recent_history_limit(user_id, limit, db=None, exclude_statuses=None, session_id=None):
        assert user_id == 7
        assert limit == 8
        assert session_id == "session-a"
        assert "pending" in (exclude_statuses or [])
        return [
            SimpleNamespace(role="user", content="session-a 的第一句"),
            SimpleNamespace(role="ai", content="session-a 的回复"),
        ]

    monkeypatch.setattr(fast_path_module, "get_common_settings_async", fake_get_common_settings_async)
    monkeypatch.setattr(fast_path_module, "get_memory_service", lambda: FakeMemoryService())
    monkeypatch.setattr(fast_path_module, "LLMService", FakeLLMService)
    monkeypatch.setattr(fast_path_module, "add_trace", fake_add_trace)
    # 基础 prompt 装配已统一到 prompt_base 模块(M5),monkeypatch 目标随之迁移
    import app.workflow.nodes.prompt_base as prompt_base_module
    monkeypatch.setattr(prompt_base_module, "get_core_system_instructions", lambda _common: "基础系统提示")
    monkeypatch.setattr(prompt_base_module, "get_character_card", lambda _user_id: None)
    monkeypatch.setattr(fast_path_module.topic_agent, "get_cached_session_summary", fake_get_cached_session_summary)
    monkeypatch.setattr(fast_path_module.history_service, "get_recent_history_limit", fake_get_recent_history_limit)

    result = await fast_path_module.standard_generate(
        {
            "user_id": 7,
            "user_input": "你还记得我们刚才聊什么吗？",
            "session_id": "session-a",
            "user_message_id": 99,
        }
    )

    context = str(captured["context"])
    trace_input = captured["trace_input"]

    assert result["response"] == "好的，我记得。"
    assert "# SESSION CHAT" in context
    assert "这是 session-a 的摘要缓存" in context
    assert "session-a 的第一句" in context
    assert trace_input["session_id"] == "session-a"
    assert trace_input["topic_summary_source"] == "session_summary_cache"


@pytest.mark.asyncio
async def test_save_snapshot_redacts_full_context_and_system_instructions(monkeypatch):
    captured_snapshot: dict[str, object] = {}

    async def fake_add_trace(_state, _node_id, input_data, output_data):
        return {"save": {"input": input_data, "output": output_data}}

    def fake_load_workflow_trace_map(_execution_id):
        return {
            "generate": {
                "input": {
                    "system_instructions": "非常长的系统提示词",
                    "full_context": "完整上下文内容\n第二行",
                },
                "output": {"final_response": "ok"},
                "timestamp": "01:02:03",
            }
        }

    def fake_save_ai_message(*, session_id, user_id, content, state_snapshot, timestamp=None, db=None):
        captured_snapshot["session_id"] = session_id
        captured_snapshot["user_id"] = user_id
        captured_snapshot["content"] = content
        captured_snapshot["state_snapshot"] = state_snapshot
        return 200

    monkeypatch.setattr(memory_module, "add_trace", fake_add_trace)
    monkeypatch.setattr(memory_module.history_service, "load_workflow_trace_map", fake_load_workflow_trace_map)
    monkeypatch.setattr(memory_module.history_service, "save_user_message", lambda **_kwargs: 100)
    monkeypatch.setattr(memory_module.history_service, "save_ai_message", fake_save_ai_message)
    monkeypatch.setattr(memory_module, "get_memory_service", lambda: SimpleNamespace(add_memory=lambda *args, **kwargs: None))

    result = await memory_module.save_memory_and_log(
        {
            "execution_id": "exec-1",
            "session_id": "session-a",
            "user_id": 7,
            "user_input": "你好",
            "response": "你好呀",
            "selected_personality": "Daisy",
            "top_emotions": [("joy", 0.9)],
            "ekman_scores": {"joy": 0.9},
            "personality_weights": {"Daisy": 1.0},
        }
    )

    snapshot = captured_snapshot["state_snapshot"]
    generate_input = snapshot["workflow_trace"]["generate"]["input"]

    assert result["ai_message_id"] == 200
    assert generate_input["system_instructions"]["redacted"] is True
    assert generate_input["full_context"]["redacted"] is True
    assert generate_input["system_instructions"]["field"] == "system_instructions"
    assert generate_input["full_context"]["field"] == "full_context"
    assert generate_input["system_instructions"]["length"] == len("非常长的系统提示词")
    assert generate_input["full_context"]["length"] == len("完整上下文内容\n第二行")
