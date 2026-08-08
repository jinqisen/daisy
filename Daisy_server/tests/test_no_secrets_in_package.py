"""
安装包不得含密钥。

坑(已实测复现):打包 spec 直接把 Daisy_server/server_config.json 塞进 app,
而源码模式下 /api/config/llm_keys 写的正是这个文件 —— 开发机上配置过一次模型,
密钥就随 .dmg 分发出去了。桌面版是 keyless 分发,安装包里不该有任何密钥。

两道防线:源文件保持干净 + 打包时强制脱敏。这里两道都测。
"""

import json
import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG = os.path.join(REPO, "Daisy_server", "server_config.json")
SPEC = os.path.join(REPO, "packaging", "daisy_backend.spec")

SECRET_KEY_PATTERN = re.compile(r"API_KEY|SECRET_KEY", re.I)


def _secret_fields(cfg: dict) -> list:
    return [k for k in cfg if SECRET_KEY_PATTERN.search(k)]


class TestRepoConfigIsClean:

    def test_config_has_no_populated_secrets(self):
        """
        源文件里的密钥字段必须为空。
        非空说明有人(或某次本地调试)把真实密钥写了进来 —— 下一次打包就会带出去。
        """
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
        populated = [k for k in _secret_fields(cfg) if cfg[k]]
        assert not populated, (
            f"server_config.json 中这些密钥字段非空: {populated} —— "
            f"打包会把它们塞进安装包分发出去"
        )


class TestSpecSanitizesBeforeBundling:
    """即便源文件被污染,打包也必须剥离 —— 不能依赖「源文件恰好干净」。"""

    def test_spec_does_not_bundle_raw_config(self):
        src = open(SPEC, encoding="utf-8").read()
        assert 'os.path.join(SERVER, "server_config.json"), "."' not in src, \
            "spec 仍在直接打包源配置文件,密钥会随包分发"

    def test_spec_uses_sanitizer(self):
        src = open(SPEC, encoding="utf-8").read()
        assert "_sanitized_config()" in src

    def test_sanitizer_actually_strips_secrets(self, tmp_path, monkeypatch):
        """
        真跑一遍脱敏函数:喂一个含密钥的配置,产物必须为空值。
        """
        import importlib.util

        dirty = {
            "MAAS_API_KEY": "sk-real-secret-value",
            "SILICONFLOW_API_KEY": "sk-another",
            "SECRET_KEY": "jwt-signing-secret",
            "LLM_PROVIDER": "huaweicloud",  # 非密钥字段应保留
        }
        fake_server = tmp_path / "Daisy_server"
        fake_server.mkdir()
        (fake_server / "server_config.json").write_text(
            json.dumps(dirty), encoding="utf-8"
        )

        # spec 不是可导入模块,直接执行其中的函数定义
        spec_src = open(SPEC, encoding="utf-8").read()
        start = spec_src.index("def _sanitized_config()")
        end = spec_src.index("datas = [")
        ns = {"os": os, "SERVER": str(fake_server)}
        exec(spec_src[start:end], ns)

        out = json.load(open(ns["_sanitized_config"](), encoding="utf-8"))
        assert out["MAAS_API_KEY"] == ""
        assert out["SILICONFLOW_API_KEY"] == ""
        assert out["SECRET_KEY"] == ""
        assert out["LLM_PROVIDER"] == "huaweicloud", "非密钥配置被误删"
        assert "sk-real-secret-value" not in json.dumps(out)
