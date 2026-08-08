"""
分析面板的数据范围回归。

用户反馈"分析面板部分模块没数据"。查下来是**数据范围错配**:
三张趋势图复用聊天界面的 visualState,而聊天历史加载带 `session_id` 过滤
(useChat.loadHistory)。于是「新建会话」后当前会话 0 条快照,面板瞬间清零。

接口层实测(不依赖浏览器):
    不带 session_id            → 12 条快照
    带新会话的 session_id      → 0 条快照

分析面板看的是**长期演化**,本就不该被会话边界切断。数据范围不同就该有自己的
数据源,而不是搭在别人的加载流程上。
"""

import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONT = os.path.join(REPO, "Daisy_front", "src")


def _src(rel: str) -> str:
    return open(os.path.join(FRONT, rel), encoding="utf-8").read()


class TestDashboardOwnsItsData:

    def test_dashboard_fetches_history_itself(self):
        """
        面板自己拉数据,而不是复用聊天界面的会话内历史。
        复用等于把"当前会话"的范围强加给"长期趋势"。
        """
        src = _src("components/AnalysisDashboard.tsx")
        assert "/api/chat/history" in src, \
            "面板未自行拉取历史 —— 会继续受聊天界面的会话过滤影响"

    def test_dashboard_request_has_no_session_filter(self):
        """
        核心回归:面板的请求**不得**带 session_id,否则新建会话即清零。
        """
        src = _src("components/AnalysisDashboard.tsx")
        idx = src.index("/api/chat/history")
        block = src[idx: idx + 400]
        assert "session_id" not in block, \
            "面板请求带了 session_id —— 新建会话后趋势图会全空"

    def test_trend_charts_use_dashboard_data(self):
        """三张趋势图都要改用面板自己的数据源。"""
        src = _src("components/AnalysisDashboard.tsx")
        for chart in ("PersonalityTrendChart personalityHistory=",
                      "EmotionTrendChart emotionHistory=",
                      "EngagementChart engagementHistory="):
            idx = src.index(chart)
            line = src[idx: src.index("\n", idx)]
            assert "visualState." not in line, \
                f"{chart.split()[0]} 仍直接用 visualState —— 会随会话切换清零"

    def test_live_updates_still_visible(self):
        """
        对话进行中产生的新数据点必须即时可见 ——
        只用历史快照会让当前这轮看不到,那是另一种"没数据"。
        """
        src = _src("components/AnalysisDashboard.tsx")
        assert "live.length > hist.length" in src, \
            "没有兼顾实时累积,当前会话新增的回合不会出现在趋势图上"


class TestChatHistoryStillSessionScoped:
    """
    对话界面**应当**按会话过滤 —— 那是它的正确语义。
    这条测试防止有人为了修面板而把聊天历史也改成跨会话(会串会话)。
    """

    def test_chat_history_keeps_session_filter(self):
        src = _src("hooks/useChat.ts")
        assert "session_id: effectiveSessionId" in src, \
            "聊天历史丢了会话过滤 —— 不同会话的消息会串在一起"


class TestSnapshotFieldsBackendContract:
    """趋势图依赖这三个字段;后端不写就是空图,且前端无从判断。"""

    def test_snapshot_carries_trend_fields(self):
        """
        快照在保存节点组装(memory.save_memory_and_log)。三个字段少任何一个,
        对应的趋势图就是空的,而前端无从判断是"没数据"还是"坏了"。
        """
        import inspect

        from app.workflow.nodes import memory

        src = inspect.getsource(memory.save_memory_and_log)
        for field in ("engagement_score", "all_emotions", "weights"):
            assert f'"{field}"' in src, f"状态快照缺少趋势图依赖的字段: {field}"
