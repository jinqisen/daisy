"""
路径解析:可写数据目录、随包分发的只读资源、本地模型。

从 config.py 拆出来的理由很简单:**它们不是配置项**。
config.py 曾同时承担"配置从哪来"和"文件在哪"两件事,
后者与前者唯一的共同点只是都用到了 `_base_dir`。

这三个函数应对的是同一个环境差异:**打包(冻结)后目录布局完全不同** ——
程序目录只读、cwd 不确定、资源被解包到 `sys._MEIPASS`。
开发机一切正常而打包版报 "Read-only file system" 或找不到文件,根因都在这里。
"""

import os
import sys
from typing import Optional

# <root>/Daisy_server —— 与 config.py 各自独立计算,避免互相 import
_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_writable_data_dir() -> str:
    """
    可写数据根目录。

    桌面打包(冻结)环境下,程序目录位于只读卷(.dmg / Applications),任何在包内
    创建目录的写操作都会抛 OSError: Read-only file system。此函数统一给出可写位置:
      - 冻结环境:DAISY_DATA_DIR(由 desktop_main 指向用户数据目录)
      - 开发/server 部署:源码树 Daisy_server/(行为与原先一致)
    """
    override = os.environ.get("DAISY_DATA_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    return _base_dir


def resolve_bundled_asset(configured_path: str) -> Optional[str]:
    """
    解析随程序分发的只读资源(如默认角色卡)的真实路径。

    配置里写的是 "./Daisy_server/assets/..." 这类**相对 cwd** 的路径 —— 只有从仓库
    根目录启动才成立。从 Daisy_server/ 启动、或打包成冻结程序(cwd 不确定,资源被
    解包到 sys._MEIPASS)时都会找不到,表现为 "Failed to load any character card"。
    这里按 cwd → 冻结解包目录 → 源码树 依次尝试,返回首个存在的路径。
    """
    if not configured_path:
        return None

    candidates = [configured_path]

    # 去掉配置里的 "Daisy_server/" 前缀后,相对包根/解包根再试一次
    rel = configured_path.lstrip("./")
    for prefix in ("Daisy_server/", "Daisy_server" + os.sep):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
            break

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, rel))
    candidates.append(os.path.join(_base_dir, rel))

    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def resolve_local_model(name: str) -> Optional[str]:
    """
    解析随包分发的本地模型目录,找不到返回 None(调用方回落到 HF Hub ID)。

    为什么需要:模型原先都用 HuggingFace Hub ID 引用,运行时按需下载。开发机有缓存
    所以从未暴露;而用户拿到的安装包是干净的 —— 第一次用到就要联网拉几百 MB 到 1GB,
    期间功能卡住,断网或网络受限直接失败。模型改为在**构建期**拉取
    (见 packaging/fetch_models.py),运行期只从本地读。
    """
    if not name:
        return None
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "model", name))
    candidates.append(os.path.join(_base_dir, "model", name))

    for path in candidates:
        if os.path.isdir(path):
            # 只有确实含权重才算数,避免半途失败留下的空目录被当成可用模型
            for root, _, files in os.walk(path):
                if any(f.endswith((".safetensors", ".bin")) for f in files):
                    return path
    return None
