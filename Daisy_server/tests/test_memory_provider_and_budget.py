"""
记忆 provider 归属 + 预算记账覆盖率的回归。

坑一(记忆):MemoryService 硬编码 `target_provider = "siliconflow"`,注释理由是
"规避 ModelArts 风控"。这个理由没有证据支撑,代价却是实打实的 ——
用户选了华为云,记忆却去调硅基流动:凭空多要一把密钥、多一份账单;
没有那把密钥时直接 raise,长期记忆的检索与写入两端全废,而用户收不到任何提示,
只会觉得"她不记得我说过的话"。记忆是对话的一部分,必须和对话用同一个模型。

坑二(预算):EXEC_BUDGET_* 默认 None(不限),而记账又只覆盖了部分调用点 ——
StrategyAgent / StyleAgent / TopicAgent 都不带 execution_id。此时设上限是**假保护**:
计数器永远到不了阈值。必须先补齐记账,再谈默认值。
"""

import ast
import inspect
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERVER = os.path.join(REPO, "Daisy_server")


class TestMemoryFollowsChatProvider:

    def test_no_hardcoded_provider(self):
        from app.services.memory import store as memory

        src = inspect.getsource(memory.MemoryService.__init__)
        # 只看真实代码行:注释里会引用这段历史,不能被误判
        code = "\n".join(
            line for line in src.splitlines() if not line.strip().startswith("#")
        )
        assert 'target_provider = "siliconflow"' not in code, \
            "记忆 LLM 又被写死成某个服务商 —— 会和用户选定的对话模型不一致"

    def test_reads_user_selected_provider(self):
        """
        必须读 common_settings.llm_provider —— 那才是对话实际使用的服务商
        (llm.py:341/433 读的就是它)。get_current_provider() 只是静态默认值,
        用它会造成"对话走硅基流动、记忆走华为云"的分裂。
        """
        from app.services.memory import store as memory

        src = inspect.getsource(memory.MemoryService.__init__)
        assert "_user_selected_provider()" in src

        helper = inspect.getsource(memory._user_selected_provider)
        assert "llm_provider" in helper
        assert "CommonSettingsDB" in helper

    def test_falls_back_instead_of_raising(self):
        """
        没有首选 provider 时应回落而不是直接废掉整个功能。
        只有一个可用的都没有时才允许失败。
        """
        from app.services.memory import store as memory

        src = inspect.getsource(memory.MemoryService.__init__)
        assert "_first_configured_provider()" in src

    def test_fallback_skips_invalidated_keys(self):
        """失效密钥不能被当作可用的回落目标,否则记忆会带着被拒的密钥反复失败。"""
        from app.services.memory import store as memory

        src = inspect.getsource(memory._first_configured_provider)
        assert "is_key_usable" in src

    def test_cache_cleared_on_provider_reload(self):
        """
        MemoryService 是 @lru_cache 单例,provider 在首次构造时定死。
        热重载密钥/切换服务商后不清缓存,记忆就一直用旧配置(或维持构造失败状态)。
        """
        from app.services.system import init_data

        src = inspect.getsource(init_data.load_llm_providers_to_redis)
        assert "get_memory_service.cache_clear()" in src

    def test_cache_cleared_on_settings_provider_switch(self):
        from app.api.routers import config as config_router

        src = inspect.getsource(config_router.update_common_settings)
        assert "get_memory_service.cache_clear()" in src


class TestBudgetMeteringCoverage:
    """
    每个 LLM 调用点都必须带 execution_id,否则不计数 —— 上限就是摆设。
    这里用 AST 静态检查,避免"加了新 agent 忘了记账"悄悄回归。
    """

    # 这些 agent 不属于单次对话执行,不参与执行级预算
    EXEMPT = {
        "DeepCharacterGenerator",  # 角色卡生成,一次性、独立于对话
        "SystemPromptGenerator",   # 配置页手动触发
        "ReflexionPatcher",        # 对话结束后的离线反思
    }

    def _agent_calls_without_execution_id(self):
        """扫描所有构造了 agent_name 的字典字面量,检查是否同时带 execution_id。"""
        offenders = []
        for root, _, files in os.walk(os.path.join(SERVER, "app")):
            if "__pycache__" in root:
                continue
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(root, fn)
                try:
                    tree = ast.parse(open(path, encoding="utf-8").read())
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Dict):
                        continue
                    keys = [k.value for k in node.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                    if "agent_name" not in keys:
                        continue
                    agent = None
                    for k, v in zip(node.keys, node.values):
                        if (isinstance(k, ast.Constant) and k.value == "agent_name"
                                and isinstance(v, ast.Constant)):
                            agent = v.value
                    if agent in self.EXEMPT:
                        continue
                    if "execution_id" not in keys:
                        offenders.append(
                            f"{os.path.relpath(path, REPO)}:{node.lineno} agent={agent}"
                        )
        return offenders

    def test_all_conversation_agents_are_metered(self):
        offenders = self._agent_calls_without_execution_id()
        assert not offenders, (
            "以下 LLM 调用点未携带 execution_id,不会计入预算账本 —— "
            "设了上限也拦不住:\n  " + "\n  ".join(offenders)
        )


class TestBudgetDefaults:

    def test_limits_are_enabled_by_default(self):
        """
        桌面版用户自付 token,不能默认无上限。
        断言字段默认值而非 settings 实例 —— 后者会被本地 .env 覆盖。
        """
        from app.core.config import settings

        fields = type(settings).model_fields
        assert fields["EXEC_BUDGET_MAX_LLM_CALLS"].default is not None, \
            "调用次数无上限 —— 异常循环会直接烧在用户账上"
        assert fields["EXEC_BUDGET_MAX_TOKENS"].default is not None

    def test_limits_leave_headroom_over_observed_peak(self):
        """
        实测一次 DEEP 对话 11 次 LLM 调用。上限太紧会误伤正常对话。
        """
        from app.core.config import settings

        fields = type(settings).model_fields
        assert fields["EXEC_BUDGET_MAX_LLM_CALLS"].default >= 20, \
            "上限低于实测峰值的合理余量,正常 DEEP 对话会被截断"
