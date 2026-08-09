"""
配置来源与优先级的回归。

配置有四层来源(真实环境变量 / server_config.json / .env / 字段默认值),
而历史上它们既没有明确的优先级,也没有任何地方能看出「当前生效的是哪一份」。
真实代价:换嵌入模型时只改了 Python 默认值,.env 与 server_config.json
还指向旧模型,排查了很久 —— 三处不一致,而报错信息完全指向别处。

这里锁住三件事:
  1. 优先级顺序(尤其是 server_config.json 必须压过 .env);
  2. Settings 只能有一个 model_config —— 曾经有两个,后者静默覆盖前者;
  3. 启动时能打印出每一项的来源。
"""

import json
import os
import re

SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PY = os.path.join(SERVER, "app", "core", "config.py")


class TestSingleModelConfig:
    """
    类体里的后一次赋值直接覆盖前一次。config.py 曾在类首写
    `SettingsConfigDict(env_file=<绝对路径>, env_file_encoding="utf-8")`,
    又在类尾写了 `ConfigDict(env_file=".env")` —— 后者赢了。
    """

    def test_only_one_model_config_assignment(self):
        src = open(CONFIG_PY, encoding="utf-8").read()
        code = "\n".join(
            l for l in src.splitlines() if not l.strip().startswith("#")
        )
        n = len(re.findall(r"^\s*model_config\s*=", code, re.M))
        assert n == 1, (
            f"config.py 中有 {n} 个 model_config 赋值 —— 后者会静默覆盖前者。"
            f"所有配置项写在同一个 SettingsConfigDict 里。"
        )

    def test_env_file_is_absolute(self):
        """
        相对路径会随 cwd 变化。打包后 cwd 不确定,pydantic 那一路会读不到 .env。
        """
        from app.core.config import Settings

        env_file = Settings.model_config.get("env_file")
        assert env_file, "model_config 没有 env_file"
        assert os.path.isabs(str(env_file)), \
            f"env_file 是相对路径 {env_file!r} —— 打包后 cwd 不确定会读不到"

    def test_encoding_is_utf8(self):
        """
        Windows 默认编码不是 UTF-8,含中文注释的 .env 会解析失败。
        这个声明曾因 model_config 被覆盖而丢失,而 Windows 打包本就未验证。
        """
        from app.core.config import Settings

        assert Settings.model_config.get("env_file_encoding") == "utf-8"

    def test_uses_settings_config_dict(self):
        """普通 ConfigDict 不保证 pydantic-settings 的 env_file 语义。"""
        src = open(CONFIG_PY, encoding="utf-8").read()
        m = re.search(r"^\s*model_config\s*=\s*(\w+)", src, re.M)
        assert m and m.group(1) == "SettingsConfigDict", \
            f"model_config 用的是 {m.group(1) if m else '?'},应为 SettingsConfigDict"


class TestPrecedenceOrder:
    """
    优先级:真实环境变量 > server_config.json > .env > 字段默认值。

    server_config.json 压过 .env 是刻意的 —— 前者是用户在界面上改出来的,
    后者只是开发者本地文件。反过来的话开发机上的 .env 会静默压掉用户设置。
    """

    KEY = "DAISY_TEST_PRECEDENCE"

    def _run(self, tmp_path, env_content, json_content, real_env=None):
        """
        直接驱动**真实的** load_config_sources,而不是在测试里重写一遍优先级。

        第一版这条测试是在子进程里自己调 load_dotenv 再 import config ——
        结果 .env 的值在 _REAL_ENV_KEYS 采集之前就进了环境,被判成"真实环境变量",
        测试于是报了个与生产行为无关的假失败。**模仿实现来测实现是靠不住的。**
        """
        from app.core.config import load_config_sources

        (tmp_path / ".env").write_text(env_content, encoding="utf-8")
        cfg = tmp_path / "server_config.json"
        cfg.write_text(json.dumps(json_content), encoding="utf-8")

        environ = dict(real_env or {})
        real_keys = frozenset(environ.keys())
        provenance = {k: "环境变量" for k in real_keys}

        load_config_sources(str(tmp_path / ".env"), str(cfg),
                            real_keys, provenance, environ=environ)
        return {
            "VALUE": environ.get(self.KEY),
            "SRC": provenance.get(self.KEY, "字段默认值"),
        }

    def test_server_config_beats_dotenv(self, tmp_path):
        """
        核心回归。这一条错了,用户在界面上的设置就会被开发者的 .env 悄悄压掉。
        """
        r = self._run(tmp_path, f"{self.KEY}=from_dotenv\n",
                      {self.KEY: "from_json"})
        assert r["VALUE"] == "from_json", \
            ".env 压过了 server_config.json —— 用户在界面上的设置会被静默忽略"
        assert r["SRC"] == "server_config.json"

    def test_real_env_beats_everything(self, tmp_path):
        """
        Docker / CI / 命令行显式指定的环境变量必须最高优先级,
        否则容器里没法覆盖打进镜像的配置。
        """
        r = self._run(tmp_path, f"{self.KEY}=from_dotenv\n",
                      {self.KEY: "from_json"},
                      real_env={self.KEY: "from_real_env"})
        assert r["VALUE"] == "from_real_env", \
            "server_config.json 压过了真实环境变量 —— 容器内无法覆盖配置"
        assert r["SRC"] == "环境变量"

    def test_dotenv_used_when_json_absent(self, tmp_path):
        """json 里没有的项仍然要能从 .env 取到,不能因为改了优先级就丢。"""
        r = self._run(tmp_path, f"{self.KEY}=from_dotenv\n", {"OTHER": "x"})
        assert r["VALUE"] == "from_dotenv"
        assert r["SRC"] == ".env"


class TestProvenanceIsObservable:
    """
    "当前生效的是哪一份"必须能一眼看到 —— 上次排查的时间几乎全花在这上面。
    """

    def test_describe_reports_source(self):
        from app.core.config import describe_config_sources

        lines = describe_config_sources(["PROJECT_NAME", "EMBEDDING_MODEL"])
        assert len(lines) == 2
        for l in lines:
            assert "来自" in l, f"来源信息缺失: {l}"

    def test_default_valued_items_show_actual_value(self):
        """
        走字段默认值的项在 os.environ 里根本不存在。若只读环境变量,
        这类项会显示成空 —— 而它恰恰最容易被误判成"没配置"。
        """
        from app.core.config import describe_config_sources

        line = describe_config_sources(["PROJECT_NAME"])[0]
        assert "PROJECT_NAME=" in line
        assert not re.search(r"PROJECT_NAME=(None)?\s*\(", line), \
            f"默认值项没有显示实际生效值: {line}"

    def test_secrets_are_masked(self):
        """来源日志会进日志文件,不能把密钥明文打出去。"""
        from app.core.config import describe_config_sources

        os.environ["TEST_FAKE_API_KEY"] = "sk-abcdef123456"
        try:
            line = describe_config_sources(["TEST_FAKE_API_KEY"])[0]
            assert "sk-abcdef123456" not in line, f"密钥被明文打印: {line}"
            assert "已设置" in line
        finally:
            os.environ.pop("TEST_FAKE_API_KEY", None)

    def test_startup_logs_sources(self):
        """接进启动流程才有用,否则只是个没人调用的函数。"""
        src = open(os.path.join(SERVER, "app", "main.py"), encoding="utf-8").read()
        assert "describe_config_sources" in src, \
            "启动流程没有打印配置来源 —— 下次三处不一致仍然要靠猜"


class TestEmptyValuesDoNotClobber:
    """
    空值表示"用户还没填这一项",不是"用户要求置空"。

    这条回归来自**真实启动**,不是设想:server_config.json 里 MAAS_API_KEY 是 "",
    而 .env 里是真实密钥。提高 json 优先级后,空串覆盖了真实值,启动日志报的却是
    `no usable LLM provider is configured` —— 指向完全无关的方向,
    排查时根本想不到是配置优先级。

    教训:**提高某个来源的优先级,就必须同时定义清楚"什么算作已配置"**。
    改之前那版规则("键已在环境中就跳过")恰好让 .env 免疫,掩盖了这个问题。
    """

    KEY = "DAISY_TEST_EMPTY"

    def _run(self, tmp_path, env_val, json_val):
        from app.core.config import load_config_sources

        (tmp_path / ".env").write_text(f"{self.KEY}={env_val}\n", encoding="utf-8")
        cfg = tmp_path / "server_config.json"
        cfg.write_text(json.dumps({self.KEY: json_val}), encoding="utf-8")
        environ, provenance = {}, {}
        load_config_sources(str(tmp_path / ".env"), str(cfg),
                            frozenset(), provenance, environ=environ)
        return environ.get(self.KEY)

    def test_empty_string_does_not_override(self, tmp_path):
        assert self._run(tmp_path, "real-key", "") == "real-key", \
            "空串覆盖了 .env 的真实值 —— 密钥会静默丢失"

    def test_whitespace_only_does_not_override(self, tmp_path):
        """界面上敲了空格再删,存下来可能是 '  '。"""
        assert self._run(tmp_path, "real-key", "   ") == "real-key"

    def test_null_does_not_override(self, tmp_path):
        assert self._run(tmp_path, "real-key", None) == "real-key"

    def test_real_value_still_overrides(self, tmp_path):
        """别矫枉过正:非空值仍然必须压过 .env。"""
        assert self._run(tmp_path, "from-env", "from-ui") == "from-ui"

    def test_zero_is_a_real_value(self, tmp_path):
        """0 / False 是有效配置值,不能被当成"没填"。"""
        assert self._run(tmp_path, "5", 0) == "0"
        assert self._run(tmp_path, "true", False) == "False"
