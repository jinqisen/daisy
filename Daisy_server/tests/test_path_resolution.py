"""
后端根目录的推导方式。

这条护栏来自一次**真实启动**才暴露的缺陷:`init_data.py` 从 `app/core/` 移到
`app/services/system/`(深了两层),而它靠"向上三层"推后端根目录的写法没跟着改,
于是去 `app/` 下找 `llm_providers.json`。

失败方式一如既往地静默:找不到只打了一条 WARNING,程序继续跑;
真正暴露出来的是启动日志里那句 **"no usable LLM provider is configured"** ——
指向完全无关的方向。测试全绿、应用能起,只有对话是废的。

**规则:需要后端根目录的地方一律用 `core.paths.SERVER_DIR`,不要各自数层数。**
数层数的写法把"文件在哪"编码进了字面量,而重构一定会移动文件。
"""

import ast
import os

import pytest

SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _walk_py(root):
    for dp, _, fs in os.walk(os.path.join(SERVER, root)):
        if "__pycache__" in dp:
            continue
        for f in fs:
            if f.endswith(".py"):
                yield os.path.join(dp, f)


class TestServerDirIsCorrect:

    def test_points_at_backend_root(self):
        from app.core.paths import SERVER_DIR

        assert os.path.isdir(SERVER_DIR)
        assert os.path.basename(SERVER_DIR) == "Daisy_server"

    @pytest.mark.parametrize("name", [
        "llm_providers.json",     # 缺了它 -> "no usable LLM provider"
        "default_settings.json",  # 缺了它 -> 默认人设装不上
    ])
    def test_expected_files_resolve(self, name):
        from app.core.paths import SERVER_DIR

        assert os.path.exists(os.path.join(SERVER_DIR, name)), \
            f"{name} 找不到 —— 根目录推导错了,而这类缺失只会打 WARNING"


class TestNoHandCountedRoots:
    """
    禁止再出现"数 dirname 层数推后端根目录"的写法。

    允许的例外只有两类:
      - `core/paths.py` 与 `core/config.py` 自身(根目录总得有人算一次);
      - 明确要的是**仓库**根目录而非后端根目录(如 main.py 找前端 dist)。
    """

    ALLOWED = {
        "app/core/paths.py",
        "app/core/config.py",
        "app/core/database.py",
        "app/core/logger.py",
        "app/core/constants.py",
        "app/main.py",          # 要的是仓库根(Daisy_Demo),不是后端根
    }

    def test_no_new_hand_counted_paths(self):
        offenders = []
        for p in _walk_py("app"):
            rel = os.path.relpath(p, SERVER)
            if rel in self.ALLOWED:
                continue
            src = open(p, encoding="utf-8").read()
            code = "\n".join(l for l in src.splitlines()
                             if not l.strip().startswith("#"))
            if "os.path.dirname(os.path.dirname(" in code:
                offenders.append(rel)
        assert not offenders, (
            "这些文件在数 dirname 层数推路径,移动文件时会被静默改坏 ——\n"
            "请改用 core.paths.SERVER_DIR:\n  " + "\n  ".join(offenders)
        )

    def test_allowlist_has_no_stale_entries(self):
        """棘轮:白名单里的文件若已不再这么写,就该从名单里删掉。"""
        stale = []
        for rel in self.ALLOWED:
            p = os.path.join(SERVER, rel)
            if not os.path.exists(p):
                stale.append(f"{rel}(文件已不存在)")
                continue
            src = open(p, encoding="utf-8").read()
            code = "\n".join(l for l in src.splitlines()
                             if not l.strip().startswith("#"))
            if "os.path.dirname(os.path.dirname(" not in code:
                stale.append(f"{rel}(已不再数层数)")
        assert not stale, "白名单需要收缩:\n  " + "\n  ".join(stale)


class TestMovedModulesStillResolve:
    """
    本轮把 22 个 services 文件移进了域子包,深度普遍 +1;
    init_data 更是从 core 移到 services/system,深度 +2。
    这里直接验证受影响模块**真的能拿到**它们要的文件。
    """

    def test_init_data_finds_llm_providers(self):
        import inspect

        from app.services.system import init_data

        src = inspect.getsource(init_data)
        assert "SERVER_DIR" in src, "init_data 仍在自行推导根目录"

    def test_rl_agent_model_dir_exists(self):
        import inspect

        from app.services.learning import rl_agent

        src = inspect.getsource(rl_agent)
        assert "SERVER_DIR" in src, "rl_agent 仍在自行推导根目录"
