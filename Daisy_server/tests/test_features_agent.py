"""
Agent 能力 feature 覆盖:情感识别、人格原型、工具循环、主动关怀、可观测性、桌面化。

补齐「功能全集」中尚无测试的部分。侧重契约与边界,不依赖网络与真实 LLM。
"""

from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parent.parent


# --- 二、情感智能 ---

class TestEmotion:
    def test_ekman_dimensions_defined(self):
        from app.core.constants import ORDERED_EMOTIONS
        assert len(ORDERED_EMOTIONS) >= 6, "Ekman 基础情绪维度不足"

    def test_six_personality_archetypes_present(self):
        """六种沟通原型(Eros/Ludus/Storge/Pragma/Mania/Agape)是策略选择的基础。"""
        prompt = (SERVER.parent / "Daisy_prompts" / "strategy" / "selection.yaml").read_text(encoding="utf-8")
        for archetype in ("Eros", "Ludus", "Storge", "Pragma", "Mania", "Agape"):
            assert archetype in prompt, f"缺少人格原型: {archetype}"

    def test_strategy_service_exposes_both_modes(self):
        """LLM 与 RL 两种策略应可切换。"""
        from app.services.persona.strategy import get_strategy_service
        svc = get_strategy_service()
        assert svc.get_strategy("llm") is not None
        assert svc.get_strategy("rl") is not None

    def test_unknown_strategy_falls_back_to_llm(self):
        from app.services.persona.strategy import get_strategy_service, LLMStrategy
        assert isinstance(get_strategy_service().get_strategy("nonexistent"), LLMStrategy)


# --- 七、工具能力(ReAct)---

class TestTools:
    def test_tools_registered(self):
        from app.services.dialogue.tools import AVAILABLE_TOOLS
        assert "search" in AVAILABLE_TOOLS
        assert "calculator" in AVAILABLE_TOOLS

    def test_tool_loop_is_bounded(self):
        """无界工具循环会导致成本失控,必须有步数上限。"""
        from app.core.config import settings
        assert settings.DEEP_TOOL_MAX_STEPS >= 1
        assert settings.DEEP_TOOL_MAX_STEPS <= 10, "步数上限过大,失去约束意义"

    def test_tool_whitelist_enforced(self):
        from app.core.config import settings
        assert settings.DEEP_ALLOWED_TOOLS, "工具白名单为空会导致任意工具可被调用"

    def test_tool_result_truncated(self):
        """工具结果需截断,避免撑爆上下文。"""
        from app.core.config import settings
        assert settings.TOOL_RESULT_MAX_CHARS > 0


# --- 六、主动关怀 ---

class TestProactive:
    def test_scheduler_registers_proactive_job(self):
        src = (SERVER / "app" / "core" / "scheduler.py").read_text(encoding="utf-8")
        assert "proactive_check_cron" in src

    def test_proactive_prompt_json_braces_escaped(self):
        """
        该 prompt 内含 JSON 示例。曾因 f-string 未转义花括号而使主动关怀 100% 崩溃
        (Invalid format specifier)。锁定不再回归。
        """
        src = (SERVER / "app" / "agents" / "daisy" / "agent.py").read_text(encoding="utf-8")
        assert '{{' in src and '}}' in src, "JSON 示例的花括号未转义,f-string 会抛 Invalid format specifier"


# --- 九、可观测性与成本控制 ---

class TestObservability:
    def test_budget_ledger_enabled_by_default(self):
        """
        默认必须限额。此前默认 None(不限)—— 桌面版用户自付 token,
        任何异常循环都直接烧在用户账上。见 test_memory_provider_and_budget.py。
        """
        from app.core.budget import evaluate_budget
        over, reason = evaluate_budget({"llm_calls": 10**6, "in_tokens": 10**9})
        assert over is True, "默认无上限,失控的执行会一直烧用户的钱"
        assert reason

    def test_budget_does_not_trip_on_normal_conversation(self, monkeypatch):
        """实测一次 DEEP 对话 11 次 LLM 调用,默认上限不能误伤它。"""
        from app.core.budget import evaluate_budget
        over, _ = evaluate_budget({"llm_calls": 11, "in_tokens": 20000, "out_tokens": 2000})
        assert over is False

    def test_budget_enforces_when_configured(self, monkeypatch):
        from app.core import budget
        from app.core.config import settings
        monkeypatch.setattr(settings, "EXEC_BUDGET_MAX_LLM_CALLS", 3)
        monkeypatch.setattr(settings, "EXEC_BUDGET_MAX_TOKENS", None)
        assert budget.evaluate_budget({"llm_calls": 3})[0] is True

    def test_trace_persisted_for_analysis(self):
        """轨迹需落库,否则无法做路由正确率/耗时分析。"""
        src = (SERVER / "app" / "services" / "memory" / "chat_history.py").read_text(encoding="utf-8")
        assert "persist_workflow_trace" in src

    def test_trajectory_analysis_script_exists(self):
        assert (SERVER / "scripts" / "analyze_trajectories.py").exists()

    def test_regression_golden_set_exists(self):
        golden = SERVER / "tests" / "golden" / "golden_dialogues.json"
        assert golden.exists()
        import json
        cases = json.loads(golden.read_text(encoding="utf-8"))["cases"]
        assert len(cases) >= 5, "黄金集用例过少,回归对比意义有限"


# --- 十、桌面化 ---

class TestDesktopMode:
    def test_embedded_mode_flag_exists(self):
        from app.core.config import settings
        assert hasattr(settings, "EMBEDDED_MODE")

    def test_embedded_forces_local_services(self, monkeypatch):
        """嵌入模式必须清空远程服务地址,否则会去连不存在的 Redis/Qdrant。"""
        from app.core.config import Settings
        s = Settings(EMBEDDED_MODE=True, QDRANT_HOST="remote.example")
        assert s.QDRANT_HOST is None, "嵌入模式未清空 QDRANT_HOST"

    def test_writable_dir_override(self, monkeypatch, tmp_path):
        """打包后程序目录只读,可写数据必须能重定向。"""
        monkeypatch.setenv("DAISY_DATA_DIR", str(tmp_path))
        from app.core.paths import get_writable_data_dir
        assert get_writable_data_dir() == str(tmp_path)

    def test_desktop_entry_exists(self):
        assert (SERVER / "desktop_main.py").exists()

    def test_electron_shell_handles_port_conflict(self):
        """端口硬编码曾导致 Errno 48 崩溃,必须有动态端口与单实例锁。"""
        main_js = (SERVER.parent / "desktop" / "main.js").read_text(encoding="utf-8")
        assert "requestSingleInstanceLock" in main_js, "缺单实例锁,重复启动会抢端口"
        assert "pickPort" in main_js or "isPortFree" in main_js, "缺动态端口探测"
