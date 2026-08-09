"""
模型随包分发 + 搜索密钥配置入口的回归。

坑一(运行时下载):嵌入模型和 Reflexion 的语义模型都用 HuggingFace Hub ID 引用,
运行时按需下载。开发机有缓存所以一直正常;用户拿到的安装包是干净的 ——
第一次用到长期记忆要联网拉 1.3GB,期间对话卡住,断网或网络受限则彻底失败。
桌面应用不该有这种"看运气"的首次体验:模型必须在**构建期**拉好、随包分发。

坑二(搜索密钥无入口):HUAWEI_SEARCH_API_KEY 此前只能手改配置文件。
缺它时联网搜索不可用,而且(修复前)还会直接抛异常打死整个对话。
现在它与 LLM 密钥同等对待:同一个配置入口 + 同一套保存前探活。
"""

import inspect
import os
import sqlite3
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONT = os.path.join(REPO, "Daisy_front", "src", "components")
MODEL_DIR = os.path.join(REPO, "Daisy_server", "model")


class TestModelsResolveLocally:

    def test_resolver_exists(self):
        from app.core.paths import resolve_local_model
        assert callable(resolve_local_model)

    def test_resolver_rejects_empty_dir(self, tmp_path, monkeypatch):
        """
        半途失败会留下空目录。把空目录当成可用模型,只会让加载在更深处炸掉,
        错误信息离根因十万八千里。
        """
        from app.core import paths as cfg   # 路径解析已从 config 移到 paths

        monkeypatch.setattr(cfg, "_base_dir", str(tmp_path))
        (tmp_path / "model" / "ghost").mkdir(parents=True)
        assert cfg.resolve_local_model("ghost") is None

    def test_resolver_accepts_dir_with_weights(self, tmp_path, monkeypatch):
        from app.core import paths as cfg   # 路径解析已从 config 移到 paths

        monkeypatch.setattr(cfg, "_base_dir", str(tmp_path))
        d = tmp_path / "model" / "real"
        d.mkdir(parents=True)
        (d / "model.safetensors").write_bytes(b"x")
        assert cfg.resolve_local_model("real") == str(d)

    def test_memory_prefers_bundled_model(self):
        from app.services.memory import store as memory

        src = inspect.getsource(memory.MemoryService.__init__)
        assert "resolve_local_model" in src, \
            "嵌入模型仍按 HF Hub ID 解析 —— 用户首次用长期记忆要联网拉 1.3GB"
        # 必须排在其它分支之前
        assert src.index("resolve_local_model") < src.index("os.path.exists(settings.EMBEDDING_MODEL_NAME)")

    def test_reflexion_metrics_prefers_bundled_model(self):
        from app.services.learning.reflexion import metrics

        src = inspect.getsource(metrics)
        assert "resolve_local_model" in src, \
            "Reflexion 的 Sentence-BERT 仍是运行时下载(~90MB),断网即失败"


class TestBuildTimeFetch:

    def test_fetch_script_exists(self):
        assert os.path.exists(os.path.join(REPO, "packaging", "fetch_models.py"))

    def test_build_script_fetches_before_packaging(self):
        """
        拉取必须发生在 PyInstaller 之前,否则打进包的是空目录。
        """
        src = open(os.path.join(REPO, "packaging", "build_macos.sh"),
                   encoding="utf-8").read()
        # 看阶段标签的顺序,而不是任一文件路径的字符串出现位置 —— 阶段里
        # 的 fetch_models.py / PyInstaller 才是真正的执行点。
        fetch_idx = src.find('"==> [1/5]')
        build_idx = src.find('"==> [3/5]')
        assert 0 <= fetch_idx < build_idx, \
            "模型拉取阶段必须排在 PyInstaller 阶段之前,否则打进去的是空目录"

    def test_spec_bundles_model_dir(self):
        src = open(os.path.join(REPO, "packaging", "daisy_backend.spec"), encoding="utf-8").read()
        assert '(os.path.join(SERVER, "model"), "model")' in src, \
            "spec 未整体打包 model/ 目录,新增模型会被漏掉"

    def test_fetch_is_idempotent(self):
        """构建会反复执行,已存在必须跳过,不能每次重下 1.3GB。"""
        src = open(os.path.join(REPO, "packaging", "fetch_models.py"), encoding="utf-8").read()
        assert "_has_weights" in src and "跳过" in src


class TestSearchKeyHasSameTreatmentAsLLMKeys:

    def test_backend_accepts_search_key(self):
        from app.api.routers.config import _KEY_ENV_NAMES
        assert "HUAWEI_SEARCH_API_KEY" in _KEY_ENV_NAMES

    @pytest.mark.asyncio
    async def test_search_key_probes_search_endpoint(self, monkeypatch):
        """
        搜索密钥必须打搜索端点。拿它去探聊天端点会得到 401,
        把一把**有效**的搜索密钥判成无效。
        """
        from app.services.system import key_verification as kv

        seen = {}

        class _Resp:
            status = 200
            async def text(self): return "{}"
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

        class _Session:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            def post(self, url, json=None, headers=None):
                seen["url"] = url
                return _Resp()

        monkeypatch.setattr(kv.aiohttp, "ClientSession", _Session)
        status, _ = await kv.verify_key("HUAWEI_SEARCH_API_KEY", "sk-x")
        assert status == kv.VALID
        assert "chat/completions" not in seen["url"]

    def test_settings_page_exposes_search_key(self):
        src = open(os.path.join(FRONT, "UserLLMConfig.tsx"), encoding="utf-8").read()
        assert "HUAWEI_SEARCH_API_KEY" in src, \
            "系统设置页没有搜索密钥入口 —— 用户只能手改配置文件"

    def test_setup_guide_exposes_search_key(self):
        src = open(os.path.join(FRONT, "LLMSetupGuide.tsx"), encoding="utf-8").read()
        assert "HUAWEI_SEARCH_API_KEY" in src

    def test_settings_page_reports_verification(self):
        """保存后要把探活结果告诉用户,而不是笼统一句"已保存"。"""
        src = open(os.path.join(FRONT, "UserLLMConfig.tsx"), encoding="utf-8").read()
        assert "verification" in src
        assert "unverified" in src


class TestEmbeddingDimsMatchModel:
    """
    维度与模型必须一致 —— 不一致时 Qdrant 拒绝写入,长期记忆**静默**失效,
    没有任何显式报错指向根因。换模型最容易漏的就是这一步。
    """

    def test_dims_is_configurable_not_hardcoded(self):
        from app.services.memory import store as memory

        src = inspect.getsource(memory.MemoryService.__init__)
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        assert "EMBEDDING_DIMS" in code
        assert '"embedding_model_dims": 1024' not in code, \
            "维度仍被写死 —— 换嵌入模型时会和实际输出对不上"

    def test_configured_model_is_the_one_bundled(self):
        """
        配置指向的模型必须**就是**打进包的那个。

        踩过的坑:改了 Python 字段默认值,却漏了 server_config.json —— 而配置文件
        优先级更高。于是包里是 bge-small,配置却指向 bge-large,
        resolve_local_model 找不到 → 回落远程 → 无密钥 → 长期记忆报错。
        此前这条测试在找不到模型时 skip,恰好把这个不一致掩盖了,故改为硬失败。
        """
        from app.core.config import settings

        name = settings.EMBEDDING_MODEL_NAME.split("/")[-1]
        bundled = [d for d in os.listdir(MODEL_DIR)
                   if os.path.isdir(os.path.join(MODEL_DIR, d))] if os.path.isdir(MODEL_DIR) else []
        if not bundled:
            pytest.skip("model/ 下尚无任何模型(构建期才拉)")
        assert name in bundled, (
            f"配置指向 {name},但包里只有 {bundled} —— "
            f"运行时找不到本地模型会回落联网下载或直接失败"
        )

    def test_config_file_agrees_with_field_default(self):
        """
        server_config.json 与 Python 字段默认值不能各说各话:配置文件优先级更高,
        只改代码默认值等于没改。
        """
        import json

        from app.core.config import settings

        cfg_path = os.path.join(REPO, "Daisy_server", "server_config.json")
        cfg = json.load(open(cfg_path, encoding="utf-8"))
        for key in ("EMBEDDING_MODEL_NAME", "EMBEDDING_DIMS"):
            if cfg.get(key) is not None:
                assert str(cfg[key]) == str(getattr(settings, key)), (
                    f"{key}: 配置文件={cfg[key]} 与生效值={getattr(settings, key)} 不一致"
                )

    def test_config_dims_match_bundled_model(self):
        """拿随包模型的 config.json 对账,这是唯一可信的事实来源。"""
        import json

        from app.core.config import settings
        from app.core.paths import resolve_local_model

        name = settings.EMBEDDING_MODEL_NAME.split("/")[-1]
        path = resolve_local_model(name)
        if not path:
            pytest.skip(f"本地未拉取 {name}(构建期才拉),跳过对账")
        cfg = json.load(open(os.path.join(path, "config.json"), encoding="utf-8"))
        assert cfg["hidden_size"] == settings.EMBEDDING_DIMS, (
            f"EMBEDDING_DIMS={settings.EMBEDDING_DIMS} 与模型实际 "
            f"{cfg['hidden_size']} 不符 —— 记忆会静默写不进去"
        )

    def test_bundled_model_wins_over_remote_embedding(self):
        """
        有随包模型时不该再走远程嵌入 —— 否则既花钱又依赖网络,
        随包分发就白做了。
        """
        from app.services.memory import store as memory

        src = inspect.getsource(memory.MemoryService.__init__)
        assert "if not _bundled and embedding_provider" in src, \
            "远程嵌入分支会无条件覆盖本地模型"


class TestMemoryHistoryDbIsWritable:
    """
    mem0 的变更历史库不得落在家目录隐藏文件夹。

    实测:打包版报 "attempt to write a readonly database"。
    向量写入照常成功,所以表面看记忆是好的 —— 只有 mem0 内部的变更历史悄悄丢了,
    这类"一半成功"的故障最难发现。
    """

    def test_history_db_in_app_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DAISY_DATA_DIR", str(tmp_path))
        from app.services.memory.store import _history_db_path

        p = _history_db_path()
        assert str(tmp_path) in p, "历史库没落在应用数据目录"
        assert ".mem0" not in os.path.expanduser("~") or not p.startswith(
            os.path.expanduser("~/.mem0")
        ), "历史库仍写在 ~/.mem0 —— 打包版无权写入"
        assert os.access(os.path.dirname(p), os.W_OK), "历史库目录不可写"

    def test_history_db_accepts_real_sqlite_write(self, tmp_path, monkeypatch):
        """
        不能只验证路径字符串;要真的能建表、插入一条记录并读回来。
        否则仍可能出现"路径看起来对,运行时 sqlite 其实写不进去"的半成功故障。
        """
        monkeypatch.setenv("DAISY_DATA_DIR", str(tmp_path))
        from app.services.memory.store import _history_db_path

        p = _history_db_path()
        con = sqlite3.connect(p)
        try:
            con.execute("CREATE TABLE IF NOT EXISTS probe(id INTEGER PRIMARY KEY, note TEXT)")
            con.execute("INSERT INTO probe(note) VALUES (?)", ("ok",))
            con.commit()
            row = con.execute("SELECT note FROM probe ORDER BY id DESC LIMIT 1").fetchone()
            assert row == ("ok",), "history.db 可打开但无法稳定写入/读回"
        finally:
            con.close()

    def test_config_passes_history_db_path(self):
        from app.services.memory import store as memory

        src = inspect.getsource(memory.MemoryService.__init__)
        assert "history_db_path" in src, \
            "未显式指定 history_db_path —— mem0 会回落到 ~/.mem0,打包版写不进去"

    def test_memory_init_logs_runtime_history_db_path(self):
        """
        运行时真实 db_path 无法在无 LLM 配置的纯单测里稳定实例化确认，
        因此先要求 MemoryService 在初始化后显式记录该路径，方便打包验证时
        直接从日志取证，而不是继续靠猜。
        """
        from app.services.memory import store as memory

        src = inspect.getsource(memory.MemoryService.__init__)
        assert "MemoryService history db" in src, \
            "未记录运行时 history db 路径 —— 打包排障时缺少关键证据"

    def test_history_db_path_is_valid_mem0_field(self):
        """字段名拼错的话 mem0 会静默忽略,等于没改。"""
        from mem0.configs.base import MemoryConfig

        assert "history_db_path" in MemoryConfig.model_fields

    def test_mem0_home_moved_off_user_home(self):
        """
        mem0 的工作目录(history.db + migrations_qdrant)默认硬编码在 ~/.mem0,
        打包版无权写入。只设 history_db_path 不够 —— migrations_qdrant 仍会落在那里,
        且 MEM0_TELEMETRY=False **不能**阻止它创建(那段代码无条件执行)。
        必须用 MEM0_DIR 整体迁走。
        """
        import os as _os

        from app.services.memory import store as memory  # 触发模块级初始化
        from mem0.memory.setup import mem0_dir

        assert _os.environ.get("MEM0_DIR"), "未设置 MEM0_DIR —— mem0 会写 ~/.mem0"
        assert not mem0_dir.startswith(_os.path.expanduser("~/.mem0")), \
            f"mem0 仍在用家目录: {mem0_dir}"

    def test_mem0_home_set_before_import(self):
        """
        必须在 import mem0 之前设置:mem0/memory/setup.py 在模块导入时就读取并建目录,
        之后再设已经晚了。
        """
        src = open(inspect.getsourcefile(__import__("app.services.memory.store",
                                                    fromlist=["memory"])),
                   encoding="utf-8").read()
        assert src.index("_init_mem0_home()") < src.index("from mem0 import Memory"), \
            "MEM0_DIR 设置晚于 import mem0 —— 目录已按默认值建好,改了也没用"

    def test_mem0_home_relocates_when_first_import_was_user_home(
        self, tmp_path, monkeypatch
    ):
        """
        回归:即使模块在更早的链路里被以 ~/.mem0 钉死,我们也要把它强制迁回
        应用数据目录,否则打包版会因 ~/.mem0 不可写而甩
        "attempt to write a readonly database"。
        """
        import importlib
        import os as _os

        # 1) 模拟"mem0 已被更早的 import 链载入、mem0_dir 仍指向 ~/.mem0"
        monkeypatch.delenv("MEM0_DIR", raising=False)
        monkeypatch.setenv("DAISY_DATA_DIR", str(tmp_path))
        from mem0.memory import setup as _mem0_setup

        _mem0_setup.mem0_dir = _os.path.join(_os.path.expanduser("~"), ".mem0")

        # 2) 重新加载 app.services.memory.store,触发 _init_mem0_home()
        if "app.services.memory.store" in sys.modules:
            importlib.reload(sys.modules["app.services.memory.store"])
        else:
            from app.services.memory import store as _memory  # noqa: F401

        from mem0.memory import setup as _mem0_setup_after

        expected = _os.path.join(str(tmp_path), "mem0")
        assert _mem0_setup_after.mem0_dir == expected, (
            f"mem0_dir 仍为 {_mem0_setup_after.mem0_dir!r},没迁到 {expected!r}"
        )
        assert _os.path.isdir(expected), "目标 mem0 目录未创建"
