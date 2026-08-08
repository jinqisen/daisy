"""
后端 sidecar 不得变成孤儿进程的回归。

实测踩到:退出客户端后,后端进程仍在,PPID=1,占 523 MB,且不再监听任何端口 ——
纯粹的内存泄漏。成因有两层:
  1. Electron 的 before-quit 只发 SIGTERM,而 uvicorn 优雅关闭要等所有连接结束;
     SSE 是长连接,永远不结束 → 后端挂住;
  2. Electron 被强杀/崩溃时 before-quit 压根不触发,连 SIGTERM 都没有。

所以两头都要有保障:外壳宽限后强杀 + 后端自己看父进程。
"""

import os
import re
import subprocess
import sys
import textwrap
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAIN_JS = os.path.join(REPO, "desktop", "main.js")


class TestShellForceKills:

    def test_before_quit_escalates_to_sigkill(self):
        src = open(MAIN_JS, encoding="utf-8").read()
        quit_block = src[src.index("app.on('before-quit'"):]
        quit_block = quit_block[:quit_block.index("app.on('window-all-closed'")]
        assert "SIGKILL" in quit_block, \
            "退出时只发 SIGTERM —— uvicorn 会因 SSE 长连接卡住,后端变孤儿"
        assert "SIGTERM" in quit_block, "应先尝试优雅关闭再强杀"


class TestBackendWatchesParent:

    def test_watchdog_is_installed_before_serving(self):
        """
        看门狗必须在 uvicorn.run 之前启动 —— uvicorn.run 是阻塞的,之后的代码不会执行。
        """
        import inspect

        sys.path.insert(0, os.path.join(REPO, "Daisy_server"))
        import desktop_main

        src = inspect.getsource(desktop_main.main)
        assert "_watch_parent_and_exit()" in src
        assert src.index("_watch_parent_and_exit()") < src.index("uvicorn.run"), \
            "看门狗在 uvicorn.run 之后启动 —— 阻塞调用会让它永远起不来"

    def test_watchdog_uses_hard_exit(self):
        """
        必须绕过优雅关闭。走正常 shutdown 又会卡在 SSE 上,等于没修。
        """
        import inspect

        sys.path.insert(0, os.path.join(REPO, "Daisy_server"))
        import desktop_main

        src = inspect.getsource(desktop_main._watch_parent_and_exit)
        assert "os._exit" in src, "用优雅退出会再次卡在 SSE 长连接上"
        assert "getppid" in src

    def test_exit_is_not_blocked_by_logging(self):
        """
        踩过的坑:外壳用管道接管 stdout,它一死管道读端就关闭,print 抛
        BrokenPipeError。若 print 裸写在 os._exit 之前,异常会杀掉看门狗线程,
        退出永远执行不到 —— 隔离测试(stdout 重定向到文件)正常,真机却残留。
        """
        import inspect

        sys.path.insert(0, os.path.join(REPO, "Daisy_server"))
        import desktop_main

        src = inspect.getsource(desktop_main._watch_parent_and_exit)
        body = src[src.index("def _loop"):]
        exit_at = body.index("os._exit")
        before_exit = body[:exit_at]
        # 退出之前若有 print,必须被 try/except 保护
        if "print(" in before_exit:
            assert "try:" in before_exit and "except" in before_exit, \
                "退出前的日志没有异常保护 —— BrokenPipeError 会让看门狗静默失效"

    def test_no_watchdog_when_run_standalone(self):
        """直接手动运行(无父进程)时不该启用,否则会自杀。"""
        import inspect

        sys.path.insert(0, os.path.join(REPO, "Daisy_server"))
        import desktop_main

        src = inspect.getsource(desktop_main._watch_parent_and_exit)
        assert "<= 1" in src or "< 2" in src, "未处理无父进程的场景"

    def test_configure_env_respects_preconfigured_data_dir(self, tmp_path, monkeypatch):
        """
        若外部已指定 DAISY_DATA_DIR,所有运行期写路径都必须跟随它。

        否则桌面包会出现"sqlite 在 A 目录、Qdrant 在 B 目录"的分裂,
        既难排查也难做隔离复现。
        """
        sys.path.insert(0, os.path.join(REPO, "Daisy_server"))
        import desktop_main

        target = tmp_path / "daisy-data"
        monkeypatch.setenv("DAISY_DATA_DIR", str(target))
        monkeypatch.delenv("VECTOR_DB_PATH", raising=False)
        monkeypatch.delenv("DAISY_DB_PATH", raising=False)
        monkeypatch.delenv("DAISY_CONFIG_PATH", raising=False)

        desktop_main._configure_env()

        assert os.environ["DAISY_DATA_DIR"] == str(target)
        assert os.environ["VECTOR_DB_PATH"] == str(target / "qdrant_embedded")
        assert os.environ["DAISY_DB_PATH"] == str(target / "daisy.db")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX 进程语义")
class TestWatchdogActuallyExits:
    """真起进程验证:父进程死后,子进程必须自行退出。"""

    def test_child_exits_when_parent_dies(self, tmp_path):
        # 复刻看门狗逻辑的独立脚本:父死 → 子退出
        child = tmp_path / "child.py"
        child.write_text(textwrap.dedent("""
            import os, sys, threading, time
            initial = os.getppid()
            def loop():
                while True:
                    time.sleep(0.2)
                    if os.getppid() != initial:
                        os._exit(0)
            threading.Thread(target=loop, daemon=True).start()
            open(sys.argv[1], "w").write(str(os.getpid()))
            time.sleep(60)   # 模拟 uvicorn 阻塞服务
        """))
        pidfile = tmp_path / "pid"

        # 父进程:拉起子进程后自己退出
        parent = tmp_path / "parent.py"
        parent.write_text(textwrap.dedent(f"""
            import subprocess, sys, time
            subprocess.Popen([sys.executable, r"{child}", r"{pidfile}"])
            time.sleep(1)
        """))

        subprocess.run([sys.executable, str(parent)], check=True, timeout=30)
        assert pidfile.exists(), "子进程没起来"
        child_pid = int(pidfile.read_text())

        # 父已退出,子应在几秒内自行消失
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                os.kill(child_pid, 0)
            except OSError:
                return  # 已退出,通过
            time.sleep(0.3)

        os.kill(child_pid, 9)  # 清理,避免污染环境
        pytest.fail("父进程退出后子进程仍存活 —— 会变成占几百 MB 的孤儿")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX 管道语义")
def test_watchdog_survives_broken_stdout_pipe(tmp_path):
    """
    真实复现:父进程像 Electron 一样用管道接管 stdout。父死后管道读端关闭,
    此时 print 抛 BrokenPipeError。裸调用会打断看门狗线程 → 后端残留。
    """
    child = tmp_path / "child.py"
    child.write_text(textwrap.dedent("""
        import os, sys, threading, time
        initial = os.getppid()
        def loop():
            while True:
                time.sleep(0.5)
                if os.getppid() != initial:
                    try:
                        print("bye", flush=True)
                    except Exception:
                        pass
                    os._exit(0)
        threading.Thread(target=loop, daemon=True).start()
        open(sys.argv[1], "w").write(str(os.getpid()))
        time.sleep(60)
    """))
    parent = tmp_path / "parent.py"
    parent.write_text(textwrap.dedent(f"""
        import subprocess, sys, time
        subprocess.Popen([sys.executable, r"{child}", sys.argv[1]],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(1.5)
    """))
    pidfile = tmp_path / "pid"
    subprocess.run([sys.executable, str(parent), str(pidfile)], check=True, timeout=30)
    assert pidfile.exists()
    pid = int(pidfile.read_text())

    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.3)
    os.kill(pid, 9)
    pytest.fail("管道断裂时看门狗失效 —— 后端会残留成几百 MB 的孤儿")
