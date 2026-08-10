"""
前端轮询节奏的护栏。

实测:一次会话的后端日志里有 **580 条** `GET /api/config/common`。
根因是 ChatInterface 固定每 3 秒轮询,而且**角色卡就绪后也不停** ——
原代码注释自己写着 "Keep polling? Maybe less frequently. // For now, let's
keep checking"。那个 "for now" 一直留到了现在。

代价:每小时 1200 次请求,每次都查库;而它等的那个事件(首次运行生成角色卡)
一辈子只发生一次。桌面版会一直开着,这是纯粹的空转。

这类问题不会报错、不会变慢到被察觉,只有翻日志才看得见 ——
和本轮其他缺陷是同一族:**失败时不报错**。
"""

import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHAT_TSX = os.path.join(REPO, "Daisy_front", "src", "components", "ChatInterface.tsx")


@pytest.fixture(scope="module")
def src():
    return open(CHAT_TSX, encoding="utf-8").read()


class TestPollingBacksOffWhenReady:

    def test_interval_is_not_fixed_at_three_seconds(self, src):
        """
        固定 3 秒 setInterval 是原来的写法 —— 它无法区分"用户正在等"
        和"早就好了"。
        """
        assert not re.search(r"setInterval\([\s\S]{0,400}?\},\s*3000\s*\)", src), \
            "仍是固定 3 秒的 setInterval —— 就绪后会永远空转"

    def test_has_distinct_ready_and_pending_intervals(self, src):
        assert "READY_POLL_MS" in src and "PENDING_POLL_MS" in src, \
            "没有区分就绪/未就绪的轮询节奏"

    def test_ready_interval_is_much_longer(self, src):
        ready = int(re.search(r"READY_POLL_MS\s*=\s*(\d+)", src).group(1))
        pending = int(re.search(r"PENDING_POLL_MS\s*=\s*(\d+)", src).group(1))
        assert ready >= pending * 5, \
            f"就绪后 {ready}ms vs 未就绪 {pending}ms —— 差距太小,省不下什么"

    def test_pending_stays_responsive(self, src):
        """
        未就绪时用户正盯着遮罩等,不能为了省请求把它拖慢。
        """
        pending = int(re.search(r"PENDING_POLL_MS\s*=\s*(\d+)", src).group(1))
        assert pending <= 5000, \
            f"未就绪时 {pending}ms 太慢 —— 用户会多等,而那正是最难熬的时刻"


class TestSkipsWhenHidden:
    """桌面版会一直开着;窗口在后台时轮询没有任何意义。"""

    def test_checks_document_hidden(self, src):
        assert "document.hidden" in src, \
            "页面不可见时仍在轮询 —— 桌面版长期挂着就是长期空转"


class TestTimerIsCleanedUp:
    """
    自排期的 setTimeout 如果不取消,组件卸载后仍会继续跑,
    并且每次挂载都会多出一条链 —— 比原来的 setInterval 更容易泄漏。
    """

    def test_cancelled_flag_and_clear_timeout(self, src):
        assert "cancelled = true" in src, "卸载时没有置取消标志"
        assert "clearTimeout" in src, "卸载时没有清掉定时器"

    def test_guard_before_rescheduling(self, src):
        """await 之后组件可能已经卸载,重排期前必须再判一次。"""
        assert re.search(r"if\s*\(cancelled\)\s*return", src), \
            "await 之后没有重新检查取消标志 —— 卸载后仍会继续排期"


class TestBuiltAssetsAreSameOrigin:
    """
    构建产物里**不能**出现写死的后端地址。

    实测踩到:一次普通的 `npm run build` 把 `127.0.0.1:30021` 烤进了产物 ——
    因为 Vite 在生产构建时也会加载 `.env.local`,而那里为开发方便写了绝对地址。
    产物在 30022 上加载后,所有请求仍打向 30021,被 CORS 拦下,
    界面永远停在"正在启动本地服务",而**后端日志里一条请求都没有**。

    对桌面版更要命:Electron 的端口是动态挑的,任何绝对地址都必然失效。

    packaging/build_macos.sh 里那句 `VITE_API_BASE_URL="" npx vite build`
    本来就是在手工规避它,但那份保护只存在于那一行脚本里 ——
    现在由 .env.production 兜底,并由这条测试守住。
    """

    DIST = os.path.join(REPO, "Daisy_front", "dist", "assets")

    def _bundles(self):
        if not os.path.isdir(self.DIST):
            pytest.skip("前端未构建(dist 不存在)")
        return [os.path.join(self.DIST, f)
                for f in os.listdir(self.DIST) if f.endswith(".js")]

    def test_no_hardcoded_backend_host(self):
        offenders = []
        for p in self._bundles():
            src = open(p, encoding="utf-8", errors="ignore").read()
            for m in re.findall(r"https?://(?:127\.0\.0\.1|localhost|\d+\.\d+\.\d+\.\d+):\d+", src):
                offenders.append(f"{os.path.basename(p)}: {m}")
        assert not offenders, (
            "构建产物里写死了后端地址,换端口/换机器即全线失效:\n  "
            + "\n  ".join(sorted(set(offenders)))
            + "\n生产构建应走同源(见 Daisy_front/.env.production)"
        )

    def test_production_env_file_pins_same_origin(self):
        """
        .env.production 必须存在且把 VITE_API_BASE_URL 置空 ——
        Vite 优先级 .env.[mode] > .env.local,靠它盖住开发用的绝对地址。
        """
        p = os.path.join(REPO, "Daisy_front", ".env.production")
        assert os.path.exists(p), \
            ".env.production 缺失 —— 普通 npm run build 会把 .env.local 的绝对地址烤进产物"
        content = open(p, encoding="utf-8").read()
        m = re.search(r"^VITE_API_BASE_URL=(.*)$", content, re.M)
        assert m and not m.group(1).strip(), \
            f"VITE_API_BASE_URL 不为空: {m.group(1) if m else '(缺失)'}"
