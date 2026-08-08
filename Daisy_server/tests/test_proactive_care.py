"""
主动关心的边界回归。

这个功能的失败方式不对称:**不够热情只是遗憾,打扰是不可逆的**
(用户觉得烦就卸载,不会回来)。所以所有参数都该偏保守,
而且改动必须留下依据 —— 历史上它们被一路调激进过,且没有任何理由记录:

    MAX_DAILY_COUNT = 5        # Increased from 3
    DEFAULT_COOLDOWN_HOURS = 2 # Decreased from 4
    忙碌保护 = 2 分钟           # Reduced from 5m to 2m

另外修了两个让功能"逻辑反转"的真缺陷,见下面对应的测试类。
"""

import datetime

import pytest


class TestParametersAreConservative:
    """
    参数由配置统一管理,且不得再被调激进。
    这些断言是**产品决策的护栏**,不是实现细节 —— 要放宽必须先拿出数据。
    """

    def test_daily_cap_is_modest(self):
        from app.core.config import settings

        assert settings.PROACTIVE_MAX_DAILY <= 3, \
            "每日主动消息超过 3 条 —— 真人朋友不会一天主动找你这么多次"

    def test_cooldown_is_hours_not_minutes(self):
        from app.core.config import settings

        assert settings.PROACTIVE_COOLDOWN_HOURS >= 3

    def test_busy_guard_is_hour_scale(self):
        """
        核心回归:忙碌保护曾被降到 **2 分钟** ——
        刚聊完两分钟又主动开口,不像陪伴,像没话找话。
        """
        from app.core.config import settings

        assert settings.PROACTIVE_BUSY_GUARD_MINUTES >= 30, \
            "忙碌保护过短,用户刚聊完就会被再次打扰"

    def test_emotion_track_does_not_increase_frequency(self):
        """
        情绪场景**不该加频**。负面情绪下说错话的代价远高于不说话,
        override 的意义是让语气更克制,不是提高打扰频率。
        """
        from app.core.config import settings

        assert (settings.PROACTIVE_EMOTION_COOLDOWN_HOURS
                >= settings.PROACTIVE_COOLDOWN_HOURS), \
            "情绪场景的冷却比常规还短 —— 在人心情不好时反而更频繁打扰"

    def test_no_hardcoded_limits_left(self):
        """参数散落在代码里会重演"悄悄调激进而无人察觉"。"""
        import inspect

        from app.services.proactive import service as proactive_service

        src = inspect.getsource(proactive_service)
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        for legacy in ("MAX_DAILY_COUNT = ", "DEFAULT_COOLDOWN_HOURS = ",
                       "OVERRIDE_COOLDOWN_HOURS = "):
            assert legacy not in code, f"仍有硬编码参数: {legacy}"


class TestQuietHours:
    """
    静默时段必须是**硬性**的。
    原先只靠"活跃概率 < 5%"判断,而冷启动默认返回 0.05,
    `0.05 < 0.05` 为假 —— 新用户毫无静默保护,半夜也会被打扰。
    """

    def _cfg(self, start, end):
        class C:
            PROACTIVE_QUIET_START_HOUR = start
            PROACTIVE_QUIET_END_HOUR = end
        return C

    def test_overnight_range_handled(self):
        """
        23:00-08:00 跨午夜。写成 start <= h < end 在跨天时永远为假,
        静默时段等于形同虚设。
        """
        from app.services.proactive.service import ProactiveService as P

        cfg = self._cfg(23, 8)
        for h in (23, 0, 3, 7):
            assert P._in_quiet_hours(h, cfg) is True, f"{h} 点应处于静默时段"
        for h in (8, 12, 22):
            assert P._in_quiet_hours(h, cfg) is False, f"{h} 点不应静默"

    def test_same_day_range_handled(self):
        from app.services.proactive.service import ProactiveService as P

        cfg = self._cfg(1, 6)
        assert P._in_quiet_hours(3, cfg) is True
        assert P._in_quiet_hours(7, cfg) is False

    def test_disabled_when_start_equals_end(self):
        from app.services.proactive.service import ProactiveService as P

        assert P._in_quiet_hours(3, self._cfg(0, 0)) is False

    def test_default_covers_night(self):
        from app.core.config import settings
        from app.services.proactive.service import ProactiveService as P

        assert P._in_quiet_hours(3, settings) is True, "凌晨 3 点默认必须静默"

    def test_check_applies_quiet_hours(self):
        import inspect

        from app.services.proactive.service import ProactiveService

        src = inspect.getsource(ProactiveService.check_and_trigger)
        assert "_in_quiet_hours" in src, "判定流程里没有静默时段检查"


class TestKnownUsersSurviveRestart:
    """
    最有价值的场景是关心"很久没联系"的用户,而原实现恰恰把它废掉了:
    用户名单来自扫描 Redis 的 `user:*:last_active`,而嵌入模式下 Redis 是
    进程内 fakeredis —— **重启即清空**;该 key 还带 24h TTL。
    合起来的效果是「用户越久不联系,越不可能收到关心」,逻辑正好反了。
    实测重启后日志为 `found 0 known users: []`,而库里有 24 条对话。
    """

    def test_known_users_read_from_db(self):
        import inspect

        from app.services.proactive.state import StateService

        src = inspect.getsource(StateService.get_all_known_users)
        assert "UserDB" in src, "用户名单仍依赖内存 Redis —— 重启后主动关心完全静默"
        assert "redis_client.keys" not in src

    def test_last_active_falls_back_to_db(self):
        """
        "离开多久了"是主动关心的核心判据。只读 Redis 的话,重启后为 None,
        而 None 会让忙碌保护直接放行 —— 刚重启就可能立刻打扰。
        """
        import inspect

        from app.services.proactive.state import StateService

        src = inspect.getsource(StateService.get_last_active_time)
        assert "ChatHistoryDB" in src, "最后活跃时间无数据库回落,重启后判据丢失"


class TestProactiveMessagesAreTraceable:
    """
    没有留痕就只能凭感觉调参 —— 而这正是那三个参数被调激进的原因。
    有了标记才能算:主动消息发出后用户是否回复。
    """

    def test_model_has_flag(self):
        from app.models.chat import ChatHistoryDB

        assert "is_proactive" in [c.name for c in ChatHistoryDB.__table__.columns]

    def test_sender_marks_messages(self):
        import inspect

        from app.services.proactive.service import ProactiveService

        src = inspect.getsource(ProactiveService._send_message)
        assert "is_proactive=True" in src, "主动消息未打标记,效果无法评估"

    def test_flag_defaults_false_for_normal_messages(self):
        """普通回复不能被误记为主动消息,否则统计全废。"""
        from app.models.chat import ChatHistoryDB

        col = ChatHistoryDB.__table__.columns["is_proactive"]
        assert col.default.arg is False
        assert col.nullable is False
