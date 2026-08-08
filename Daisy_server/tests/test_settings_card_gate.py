"""
「角色卡生成中」永久转圈的回归。

坑:保存设置的 POST /api/config/common 里内联 await 深度角色卡生成,既无超时也无
兜底。深度卡输出 2000+ tokens,常超过通用 60s 超时(且还重试一次 → 122s),失败后
character_card_json 保持 NULL,前端门禁永不解除 —— 用户看到的就是一直转圈,
而且这个 HTTP 请求本身被阻塞两分钟。

根因是同一件事有两份实现:auth.generate_card_background 有超时和默认卡兜底,
config 路由却自己又写了一遍裸调用。测试同时锁住行为和「不再有第二份实现」。
"""

import inspect

import pytest

from app.api.routers import config as config_router
from app.core.config import settings


class TestTimeoutBudgetIsCoherent:

    def test_inner_llm_timeout_is_shorter_than_outer_guard(self):
        """
        内层单次请求超时必须小于外层 asyncio 保护,否则外层永远等不到它先失败。
        原值:内层 60s×2 次重试 = 122s > 外层 90s。
        """
        assert settings.DEEP_CARD_LLM_TIMEOUT_SEC < settings.DEEP_CARD_TIMEOUT_SEC, (
            f"内层 {settings.DEEP_CARD_LLM_TIMEOUT_SEC}s 不小于外层 "
            f"{settings.DEEP_CARD_TIMEOUT_SEC}s —— 外层超时保护会形同虚设"
        )

    def test_deep_card_gets_more_time_than_a_normal_chat(self):
        """角色卡是一次性大输出,不该沿用聊天的通用超时。"""
        assert settings.DEEP_CARD_LLM_TIMEOUT_SEC > 60


class TestDeepGenerationCallSite:
    """深度生成必须显式传超时且不重试 —— 重试只会让用户多等一倍。"""

    def test_generation_passes_explicit_timeout(self):
        from app.services.dialogue import generation
        src = inspect.getsource(generation.generate_deep_character_card)
        assert "DEEP_CARD_LLM_TIMEOUT_SEC" in src, \
            "深度卡生成未指定专用超时,会沿用 60s 通用值并超时失败"
        assert "max_retries=0" in src, \
            "深度卡生成仍会重试 —— 失败耗时翻倍,且已有默认卡兜底不需要重试"


class TestSettingsRouteDoesNotBlockOnGeneration:

    def test_common_settings_does_not_await_deep_generation_inline(self):
        """
        核心回归:保存设置不得内联 await 深度生成。
        内联意味着请求被阻塞两分钟,且失败时没有任何卡落库。
        """
        src = inspect.getsource(config_router.update_common_settings)
        assert "await generate_deep_character_card" not in src, \
            "保存设置仍在内联等待深度生成 —— 请求会被阻塞,失败后角色卡为空"

    def test_common_settings_writes_a_baseline_card(self):
        """无卡时必须立刻落默认卡,否则前端门禁不开。"""
        src = inspect.getsource(config_router.update_common_settings)
        assert "load_default_character_card" in src, \
            "保存设置时未落默认卡 —— 深度生成失败就会一直卡在「角色卡生成中」"

    def test_common_settings_defers_generation_to_background(self):
        src = inspect.getsource(config_router.update_common_settings)
        assert "background_tasks.add_task" in src

    def test_generation_reuses_the_guarded_helper(self):
        """
        复用 auth.generate_card_background(自带超时 + 兜底),
        而不是再写第三份裸调用 —— 分叉实现正是本 bug 的成因。
        """
        src = inspect.getsource(config_router.update_common_settings)
        assert "generate_card_background" in src, \
            "又出现了一份独立的角色卡生成实现,超时/兜底会再次漏掉"
