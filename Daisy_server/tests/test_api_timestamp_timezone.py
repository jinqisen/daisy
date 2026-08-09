"""
接口返回的时间必须带时区标记。

这条来自看分析面板时的实测:一轮 **12:41** 的对话,「AI 回复质量评价趋势」
上显示成 **04:41** —— 正好差一个时区。

机制:库里存的是 naive UTC(见 core/time_utils.utc_now_naive),接口直接
`.isoformat()` 得到 `2026-08-09T04:41:18`,**不带偏移**;浏览器的
`new Date("2026-08-09T04:41:18")` 按规范把无偏移的日期时间当作**本地时间**,
于是 UTC+8 的用户看到的每个时间点都早 8 小时。

它不报错、不崩溃,只是所有时间轴整体平移 —— 又是"失败时不报错"那一类,
而且比前几个更隐蔽:图表看起来完全正常,只是横轴是错的。
"""

import ast
import datetime
import os

import pytest

SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestHelper:

    def test_appends_utc_offset(self):
        from app.core.time_utils import naive_utc_to_iso

        out = naive_utc_to_iso(datetime.datetime(2026, 8, 9, 4, 41, 18))
        assert out.endswith("+00:00"), f"没有时区标记: {out}"

    def test_browser_parses_it_as_utc(self):
        """
        等价验证浏览器行为:带偏移的字符串解析出的 epoch,
        必须与把它当 UTC 解释一致(差值为 0),而裸字符串会差一个时区。
        """
        from app.core.time_utils import naive_utc_to_iso

        naive = datetime.datetime(2026, 8, 9, 4, 41, 18)
        parsed = datetime.datetime.fromisoformat(naive_utc_to_iso(naive))
        expected = naive.replace(tzinfo=datetime.timezone.utc)
        assert parsed == expected
        # 裸写法则会被当成本地时间 —— 这正是缺陷本身
        bare = datetime.datetime.fromisoformat(naive.isoformat())
        assert bare.tzinfo is None

    def test_none_passthrough(self):
        from app.core.time_utils import naive_utc_to_iso

        assert naive_utc_to_iso(None) is None

    def test_tz_aware_input_unchanged(self):
        """已经带时区的值不该被二次加工。"""
        from app.core.time_utils import naive_utc_to_iso

        aware = datetime.datetime(2026, 8, 9, 4, 0, tzinfo=datetime.timezone.utc)
        assert naive_utc_to_iso(aware) == aware.isoformat()


class TestNoBareIsoformatAtApiBoundary:
    """
    禁止再对库里取出的时间直接 `.isoformat()`。

    用 AST 找形如 `<某某>.timestamp.isoformat()` 的调用 —— 这类值一定来自
    数据库行(库里的约定是 naive UTC),裸序列化就会丢时区。
    """

    def _offenders(self, *roots):
        found = []
        for root in roots:
            for dp, _, fs in os.walk(os.path.join(SERVER, root)):
                if "__pycache__" in dp:
                    continue
                for f in fs:
                    if not f.endswith(".py"):
                        continue
                    path = os.path.join(dp, f)
                    tree = ast.parse(open(path, encoding="utf-8").read())
                    for node in ast.walk(tree):
                        if not (isinstance(node, ast.Call)
                                and isinstance(node.func, ast.Attribute)
                                and node.func.attr == "isoformat"):
                            continue
                        inner = node.func.value
                        # 只盯 x.timestamp.isoformat();utc_now_iso 等自有助手不算
                        if (isinstance(inner, ast.Attribute)
                                and inner.attr in ("timestamp", "created_at", "updated_at")):
                            found.append(f"{os.path.relpath(path, SERVER)}:{node.lineno}")
        return found

    def test_api_layer_is_clean(self):
        bad = self._offenders("app/api")
        assert not bad, (
            "接口层直接序列化了库里的时间(会丢时区,前端整轴偏一个时区):\n  "
            + "\n  ".join(bad) + "\n请改用 core.time_utils.naive_utc_to_iso"
        )

    def test_services_layer_is_clean(self):
        """SSE 推送的时间同样会进前端。"""
        bad = self._offenders("app/services")
        assert not bad, (
            "服务层直接序列化了库里的时间:\n  " + "\n  ".join(bad)
            + "\n请改用 core.time_utils.naive_utc_to_iso"
        )


class TestReflexionHistoryEndpoint:
    """分析面板的「AI 回复质量评价趋势」直接吃这个接口的 timestamp。"""

    def test_uses_helper(self):
        src = open(os.path.join(SERVER, "app", "api", "routers", "chat.py"),
                   encoding="utf-8").read()
        idx = src.index("reflexion/history")
        block = src[idx: idx + 1600]
        assert "naive_utc_to_iso" in block, \
            "reflexion 历史接口仍返回不带时区的时间 —— 面板横轴会偏一个时区"
