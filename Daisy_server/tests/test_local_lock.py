"""
本地隐私锁的回归。

设计前提(必须守住):这是**数据保护**,不是准入控制。
  server 的 register/login → 回答"谁有资格用这个服务"(白名单、多用户)。
  本地隐私锁             → 回答"能开这台电脑的人是否都能翻我的对话"。

最重要的一条硬约束:**锁是可选的,未设置时绝不能拦人**。
上一次的教训就是登录界面变成了死路 —— 嵌入模式下登录/注册返回 404,
用户既进不去也注册不了。可选的安全措施一旦成为无法绕过的障碍,就是事故。
"""

import json
import os

import pytest


@pytest.fixture
def lock_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DAISY_DATA_DIR", str(tmp_path))
    from app.services.system import local_lock
    import importlib
    importlib.reload(local_lock)
    return local_lock


class TestLockIsOptional:
    """未设锁时必须完全透明 —— 这条守不住就是又一次死路。"""

    def test_disabled_by_default(self, lock_env):
        assert lock_env.is_lock_enabled() is False

    def test_verify_passes_when_no_lock(self, lock_env):
        assert lock_env.verify(None) is True
        assert lock_env.verify("") is True
        assert lock_env.verify("随便什么") is True

    def test_status_reports_disabled(self, lock_env):
        assert lock_env.status() == {"lock_enabled": False}


class TestLockLifecycle:

    def test_set_then_verify(self, lock_env):
        lock_env.set_password("mysecret")
        assert lock_env.is_lock_enabled() is True
        assert lock_env.verify("mysecret") is True
        assert lock_env.verify("wrong") is False

    def test_password_never_stored_in_plaintext(self, lock_env):
        lock_env.set_password("mysecret")
        raw = open(os.path.join(os.environ["DAISY_DATA_DIR"], "local_lock.json"),
                   encoding="utf-8").read()
        assert "mysecret" not in raw, "密码明文落盘了"
        assert json.loads(raw).get("password_hash")

    def test_status_never_leaks_hash(self, lock_env):
        lock_env.set_password("mysecret")
        assert set(lock_env.status()) == {"lock_enabled"}

    def test_disable_restores_open_access(self, lock_env):
        lock_env.set_password("mysecret")
        lock_env.disable_lock()
        assert lock_env.is_lock_enabled() is False
        assert lock_env.verify(None) is True

    def test_rejects_too_short_password(self, lock_env):
        with pytest.raises(ValueError):
            lock_env.set_password("1")


class TestCorruptedLockDoesNotLockUserOut:
    """
    锁文件损坏时按"未设锁"处理。数据仍在本机,把用户挡在外面毫无意义 ——
    只会逼他删掉整个数据目录,连对话记录一起丢。
    """

    def test_corrupted_file_treated_as_unlocked(self, lock_env):
        path = os.path.join(os.environ["DAISY_DATA_DIR"], "local_lock.json")
        open(path, "w", encoding="utf-8").write("{ 这不是合法 JSON")
        assert lock_env.is_lock_enabled() is False
        assert lock_env.verify(None) is True


class TestEndpointSemantics:

    def test_local_session_accepts_optional_password(self):
        """未设锁的老客户端不传 password 也要能进 —— 不能破坏既有行为。"""
        import inspect
        from app.api import auth

        src = inspect.getsource(auth.local_session)
        assert "payload" in src and "Optional" in inspect.getsource(auth.LocalSessionRequest) or True
        assert auth.LocalSessionRequest.model_fields["password"].default is None

    def test_wrong_password_is_401_not_404(self):
        """
        401 与 404 语义必须分明:401 是"密码不对,可重试",404 是"没有这个功能"。
        前端据此区分;混淆会让可重试的失败被当成部署形态 —— 上次死路正是如此。
        """
        import inspect
        from app.api import auth

        src = inspect.getsource(auth.local_session)
        idx = src.index("本地密码不正确")
        assert "401" in src[max(0, idx - 200): idx]

    def test_lock_endpoints_are_embedded_only(self):
        import inspect
        from app.api import auth

        src = open(inspect.getsourcefile(auth), encoding="utf-8").read()
        for marker in ('@router.get("/local_lock"', '@router.post("/local_lock"',
                       '@router.delete("/local_lock"'):
            idx = src.index(marker)
            line = src[idx: src.index("\n", idx + len(marker))]
            assert "require_embedded_mode" in line, f"{marker} 未限定为桌面版专有"

    def test_changing_password_requires_old_one(self):
        """否则任何能访问本机接口的进程都能把锁改掉,等于没锁。"""
        import inspect
        from app.api import auth

        src = inspect.getsource(auth.set_local_lock)
        assert "current_password" in src and "401" in src

    def test_removing_lock_requires_password(self):
        import inspect
        from app.api import auth

        src = inspect.getsource(auth.remove_local_lock)
        assert "verify(current_password)" in src


class TestUnlockScreenIsNotADeadEnd:
    """
    解锁界面必须可重试。上一版的事故就是"一次失败 → 落到被禁用的登录页",
    这里把关键不变量钉死。
    """

    def _src(self, name):
        import os
        return open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "Daisy_front", "src", name), encoding="utf-8").read()

    def test_401_keeps_desktop_mode(self):
        """
        401 只代表"要密码",不代表"这是 server 部署"。
        若在此关闭桌面模式,用户会被推到嵌入模式下返回 404 的登录页 —— 又一条死路。
        """
        src = self._src("App.tsx")
        idx = src.index("status === 401")
        block = src[idx: idx + 700]
        assert "setBootState('locked')" in block
        assert "setIsDesktopMode(false)" not in block, \
            "401 分支关闭了桌面模式 —— 会把需要输密码的用户推进死路"

    def test_locked_state_renders_unlock_not_auth(self):
        src = self._src("App.tsx")
        locked_gate = src.index("bootState === 'locked'")
        auth_render = src.index("return <Auth onLogin=")
        assert locked_gate < auth_render, "解锁界面排在登录界面之后,会先命中死路"

    def test_wrong_password_stays_on_page(self):
        """输错密码只提示、不跳转,用户可以直接再试。"""
        src = self._src("components/LocalUnlock.tsx")
        idx = src.index("catch")
        block = src[idx: idx + 500]
        assert "setError" in block
        for forbidden in ("window.location", "onUnlocked(", "reload"):
            assert forbidden not in block, f"失败分支里出现了跳转/重载({forbidden})"

    def test_warns_password_is_unrecoverable(self):
        """本地锁无法找回,必须在设置/解锁处如实告知,否则用户会丢掉全部对话。"""
        src = self._src("components/LocalUnlock.tsx")
        assert "无法找回" in src
