# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec:把 Daisy 后端(FastAPI + 单进程嵌入模式)打成可执行。

产物为 onedir(BUNDLE 目录),由 Tauri sidecar 拉起。资源随包:
  Daisy_prompts/  model/  frontend/
用户数据在运行期写入 ~/Library/Application Support/Daisy。

重型依赖(torch/transformers 等)由 PyInstaller hooks 处理,其余用 collect_all 兜底。
"""
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(os.path.dirname(SPECPATH), "."))
SERVER = os.path.join(ROOT, "Daisy_server")

# 关键:collect_submodules("app") 需要 app 在 sys.path 才能枚举到子模块,
# 否则返回空,导致 app 包完全不进包(ModuleNotFoundError: No module named 'app')。
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)

def _sanitized_config():
    """
    生成 server_config.json 的脱敏副本供打包使用。

    为什么不能直接打包源文件:源码模式下 /api/config/llm_keys 就是写这个文件,
    开发机上配置过一次,密钥便随 .dmg 一起分发(已实测复现)。
    桌面版是 keyless 分发 —— 安装包里不该有任何密钥。
    """
    import json
    import tempfile

    src = os.path.join(SERVER, "server_config.json")
    with open(src, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    stripped = [k for k in cfg
                if ("API_KEY" in k.upper() or k.upper() == "SECRET_KEY") and cfg[k]]
    for k in stripped:
        cfg[k] = ""
    if stripped:
        print(f"[spec] 已从随包配置中剥离密钥: {stripped}")

    out_dir = tempfile.mkdtemp(prefix="daisy_cfg_")
    out = os.path.join(out_dir, "server_config.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return out


datas = [
    (os.path.join(ROOT, "Daisy_prompts"), "Daisy_prompts"),
    # 本地模型:整个 model/ 目录随包分发。
    # 这些模型原先用 HF Hub ID 引用、运行时按需下载 —— 开发机有缓存所以没暴露,
    # 用户第一次用到长期记忆/反思就要联网拉 1.4GB,断网则彻底失败。
    # 构建期由 packaging/fetch_models.py 拉好(见 build_macos.sh 第 1 步)。
    (os.path.join(SERVER, "model"), "model"),
    (os.path.join(ROOT, "Daisy_front", "dist"), "frontend"),
    # 运行期需要的配置资产
    (os.path.join(SERVER, "llm_providers.json"), "."),
    (os.path.join(SERVER, "default_settings.json"), "."),
    (os.path.join(SERVER, "whitelist.json"), "."),
    # 默认配置:打包的是**脱敏副本**(见下方 _sanitized_config)。
    # 曾经直接打包源文件,而 /api/config/llm_keys 在源码模式下正是写这个文件 ——
    # 开发机上跑一次配置,密钥就随 .dmg 分发出去了(实测复现)。
    (_sanitized_config(), "."),
    # 角色卡资产:深度角色卡生成失败时的兜底。缺失会导致前端永远卡在
    # "构建数字灵魂/角色卡生成中"(get_character_card 抛 CRITICAL)。
    (os.path.join(SERVER, "assets", "character_cards"), "assets/character_cards"),
]
binaries = []
hiddenimports = []

# collect_all:把包的 py 模块 + 数据文件 + 动态库全量纳入(应对动态导入)
for pkg in [
    "torch", "transformers", "sentence_transformers", "tokenizers",
    "qdrant_client", "mem0", "litellm", "langchain", "langchain_core",
    # fakeredis 已移除:嵌入模式改用进程内缓存(core/local_kv.py),
    # 全库不再有任何 import。留着只会让安装包多带一个用不到的依赖。
    "langchain_openai", "langgraph", "tiktoken", "tiktoken_ext",
    "arq", "structlog", "passlib", "jose", "apscheduler", "jieba",
    "sqlalchemy", "pydantic", "pydantic_settings",
    # 角色卡等结构化输出的 JSON 容错解析(见 core/json_utils.py)
    "json_repair",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:
        print(f"[spec] collect_all skipped {pkg}: {e}")

hiddenimports += collect_submodules("app")
hiddenimports += ["uvicorn", "uvicorn.logging", "uvicorn.loops.auto",
                  "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto",
                  "uvicorn.lifespan.on", "email_validator", "argon2"]

a = Analysis(
    [os.path.join(SERVER, "desktop_main.py")],
    pathex=[SERVER],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "PySide6", "notebook", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="daisy_backend",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="daisy_backend",
)
