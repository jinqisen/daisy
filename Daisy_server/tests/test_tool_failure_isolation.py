"""
可选工具失败不得中断对话 + 崩溃遗留消息不得自动重放。

实测事故链(打包版全新安装,只配了聊天密钥、没配搜索密钥):
  1. 用户提到"查天气" → ReAct 决定调搜索工具;
  2. SearchTool 因无密钥直接 raise;
  3. tool_check 把它包成 NodeError 往上抛 → **整个 chat_task 挂掉**;
  4. 消息停在 pending,再没人处理;
  5. 用户之后每次触发处理,这条旧消息就被重放一次 ——
     用户看到的是"一点发送就自动发出之前那条消息"。

搜索是**增强**能力,不是对话的必要条件。缺一把可选密钥绝不该让人说不了话。
"""

import inspect

import pytest


class TestToolFailureDegrades:

    def test_single_tool_error_does_not_abort_loop_node(self):
        """单个工具抛错只跳过它,不能让节点失败。"""
        from app.workflow.nodes import react

        src = inspect.getsource(react.tool_check)
        # 工具调用必须被单独保护
        assert "except Exception as tool_err" in src, \
            "工具调用没有单独的异常保护 —— 一个工具不可用会拖垮整个节点"

    def test_node_never_raises_node_error(self):
        """
        核心回归:tool_check 不得向上抛异常。
        它一抛,chat_task 就挂,消息永久 pending。
        """
        from app.workflow.nodes import react

        src = inspect.getsource(react.tool_check)
        assert 'raise NodeError("ToolCheck"' not in src, \
            "工具节点仍会抛 NodeError —— 缺一把可选密钥就会让用户说不了话"

    def test_degraded_path_returns_empty_tool_results(self):
        from app.workflow.nodes import react

        src = inspect.getsource(react.tool_check)
        tail = src[src.rindex("except Exception"):]
        assert "tool_results" in tail and "{}" in tail, \
            "降级路径未返回空 tool_results,下游汇聚会拿到缺失的键"

    @pytest.mark.asyncio
    async def test_search_tool_without_key_is_catchable(self):
        """
        搜索工具在无密钥时抛的异常必须是普通异常,能被上层 catch。
        (这里只验证它确实抛而不是静默返回错误字符串 —— 两种都可接受,
        但行为要明确,上层据此设计。)
        """
        from app.services.dialogue.tools import SearchTool
        from app.core.config import settings

        original = settings.HUAWEI_SEARCH_API_KEY
        try:
            settings.HUAWEI_SEARCH_API_KEY = None
            tool = SearchTool()
            try:
                result = await tool.run("test")
                # 若不抛异常,则必须返回可识别的错误信息而非崩溃
                assert isinstance(result, str)
            except Exception as e:
                assert "not configured" in str(e).lower() or "key" in str(e).lower()
        finally:
            settings.HUAWEI_SEARCH_API_KEY = original


class TestStalePendingReclaimed:
    """崩溃遗留的 pending 消息必须在启动时回收,否则会集体自动重放。"""

    def test_startup_reclaims_stale_messages(self):
        from app import main

        src = inspect.getsource(main.lifespan) if hasattr(main, "lifespan") else open(
            main.__file__, encoding="utf-8"
        ).read()
        assert "pending" in src and "processing" in src, \
            "启动时未回收遗留消息 —— 崩溃后重启会自动重放用户之前的消息"
        assert "failed" in src

    def test_reclaim_happens_before_scheduler(self):
        """
        必须在调度器/任务系统启动前回收,否则回收与重放会赛跑。
        """
        src = open(__import__("app.main", fromlist=["main"]).__file__, encoding="utf-8").read()
        reclaim = src.index('status.in_(["pending", "processing"])')
        scheduler = src.index("scheduler_manager.start()")
        assert reclaim < scheduler, "回收发生在调度器启动之后,可能与重放竞争"


class TestRetryIsDeliberate:
    """重试要用户明确确认 —— 误触一次就重跑一整轮对话,是真金白银。"""

    def test_retry_requires_confirmation(self):
        import os

        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "Daisy_front", "src", "components", "ChatInterface.tsx",
        )
        src = open(path, encoding="utf-8").read()
        idx = src.index("item.status === 'error'")
        block = src[idx: idx + 900]
        assert "Modal.confirm" in block, \
            "失败重试仍是点一下就重发 —— 误触成本是一整轮对话"
        assert "Tooltip" in block, "重试图标没有任何说明文案,用户不知道点了会发生什么"
