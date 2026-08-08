"""
后端就绪状态机的回归 —— 防止"启动慢"再次被误判成"这是 server 部署"。

实测事故:
  用户正常启动应用,看到的却是登录界面;而登录/注册在嵌入模式下被刻意禁用
  (require_server_mode → 404),于是无论注册还是登录都报 not found —— 死路。

根因不是认证本身,而是**没人负责"后端还没起来"这个状态**:
  后端要加载 torch/transformers,实测 30~45 秒才就绪;
  前端只试一次 local_session,任何失败都当成"非嵌入模式",落到被禁用的登录界面。
把**瞬时不可用**误判成**部署形态**,是这次事故的本质。
"""

import inspect
import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP_TSX = os.path.join(REPO, "Daisy_front", "src", "App.tsx")


def _app_source() -> str:
    return open(APP_TSX, encoding="utf-8").read()


class TestBackendGatesAreConsistent:
    """后端两端的门禁必须自洽:禁用登录的同时,必须保证免登录通道可用。"""

    def test_login_register_disabled_in_embedded_mode(self):
        from app.api import auth

        src = open(inspect.getsourcefile(auth), encoding="utf-8").read()
        for name in ('@router.post("/login"', '@router.post("/register"'):
            idx = src.index(name)
            line = src[idx: src.index("\n", idx)]
            assert "require_server_mode" in line, f"{name} 未在嵌入模式禁用"

    def test_local_session_available_in_embedded_mode(self):
        """
        这是嵌入模式下**唯一**的入口。它若不可用,用户没有任何其它路径进入应用。
        """
        from app.api import auth

        src = open(inspect.getsourcefile(auth), encoding="utf-8").read()
        idx = src.index('@router.post("/local_session"')
        line = src[idx: src.index("\n", idx)]
        assert "require_server_mode" not in line, \
            "免登录入口也被 server 门禁挡住 —— 嵌入模式将完全无法进入"


class TestFrontendDistinguishesTransientFromDeployment:

    def test_boot_state_machine_exists(self):
        src = _app_source()
        assert "bootState" in src, "没有就绪状态机 —— 启动期失败会被当成部署形态"
        for state in ("'starting'", "'ready'", "'server-mode'", "'error'"):
            assert state in src, f"缺少状态 {state}"

    def test_only_404_implies_server_mode(self):
        """
        核心回归:只有后端明确答复 404 才能判定为 server 部署。
        连接失败/5xx 是"还没起来",据此关闭桌面模式会把用户推进死路。

        不用固定窗口截取(会因代码位置漂移而误判),直接对全文逐个检查:
        每一处关闭桌面模式的调用,前面都必须有 404 判定。
        """
        # 只看真实代码行:注释里会引用这段历史,连注释一起匹配会自己打自己
        src = "\n".join(
            line for line in _app_source().splitlines()
            if not line.strip().startswith("//")
        )
        assert "status === 404" in src, \
            "未区分 404 与瞬时失败 —— 启动慢会被误判成 server 部署"

        hits = list(re.finditer(r"setIsDesktopMode\(false\)", src))
        assert hits, "找不到关闭桌面模式的调用,测试锚点已失效"
        for m in hits:
            preceding = src[max(0, m.start() - 500): m.start()]
            assert "404" in preceding, \
                "存在不以 404 为前提就关闭桌面模式的分支 —— " \
                "后端还在启动时用户会掉进被禁用的登录界面"

    def test_retries_while_starting(self):
        """启动期必须重试,否则一次瞬时失败就永久停住。"""
        src = _app_source()
        assert re.search(r"setTimeout\(\(\)\s*=>\s*\{[^}]*validate\(\)", src), \
            "启动期不重试 —— 一次失败就永久停在错误状态"

    def test_retry_has_deadline(self):
        """无限重试会让真正的故障永远显示"启动中",用户不知道发生了什么。"""
        src = _app_source()
        assert "bootDeadlineRef" in src
        assert "'error'" in src, "重试超时后没有可见的失败状态"

    def test_starting_state_does_not_render_login(self):
        """
        启动中必须显示"正在启动",而不是登录界面 ——
        嵌入模式下登录界面是死路(登录/注册均 404)。
        """
        src = _app_source()
        starting_gate = src.index("bootState === 'starting'")
        auth_render = src.index("return <Auth onLogin=")
        assert starting_gate < auth_render, \
            "登录界面的渲染分支排在'启动中'之前 —— 冷启动期间会先看到死路"
