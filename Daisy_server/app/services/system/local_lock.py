"""
本地隐私锁 —— 桌面版的"设备密码",与 server 部署的注册/登录是两回事。

区别必须讲清楚,否则很容易把两套逻辑又搅在一起(上次登录死路就是这么来的):

  server 的 register/login  = **准入控制**。回答"谁有资格使用这个服务",
                              涉及白名单、多用户、账号体系。桌面版没有这个问题:
                              装在你机器上的软件,不需要向谁证明你有资格用。

  本地隐私锁                 = **数据保护**。回答"能打开这台机器的人,
                              是否都能翻看这些对话"。密码只在本地校验,
                              hash 存本地,不上传、不可找回。

关键设计:**锁是可选的**。未设置时直接进入,不阻塞任何人 ——
这条是硬约束:上次的教训就是登录界面变成了死路(嵌入模式下登录接口返回 404,
用户既进不去也无法注册)。可选的安全措施绝不能成为无法绕过的障碍。
"""

import json
import os
from typing import Optional

import structlog

from app.core import security
from app.core.paths import get_writable_data_dir

logger = structlog.get_logger()

_LOCK_FILE = "local_lock.json"


def _lock_path() -> str:
    return os.path.join(get_writable_data_dir(), _LOCK_FILE)


def is_lock_enabled() -> bool:
    """是否已设置本地锁。未设置时应用直接可用,不做任何拦截。"""
    path = _lock_path()
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("password_hash"))
    except Exception as e:
        # 锁文件损坏时**不能**把用户锁在外面 —— 数据仍在本机,
        # 让用户进不去毫无意义,只会逼他删数据目录。
        logger.warning(f"本地锁配置损坏,按未设锁处理: {e}")
        return False


def set_password(password: str) -> None:
    """设置/修改本地锁密码。只存 hash,明文不落盘。"""
    if not password or len(password) < 4:
        raise ValueError("密码至少 4 位")
    path = _lock_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"password_hash": security.get_password_hash(password)}, f)
    logger.info("本地隐私锁已设置")


def disable_lock() -> None:
    """关闭本地锁(需先通过校验,由调用方保证)。"""
    path = _lock_path()
    if os.path.exists(path):
        os.remove(path)
    logger.info("本地隐私锁已关闭")


def verify(password: str) -> bool:
    """校验密码。未设锁时任何输入都算通过 —— 没有锁就没有门。"""
    if not is_lock_enabled():
        return True
    try:
        with open(_lock_path(), "r", encoding="utf-8") as f:
            stored = json.load(f).get("password_hash")
        return bool(stored) and security.verify_password(password or "", stored)
    except Exception as e:
        logger.error(f"本地锁校验失败: {e}")
        return False


def status() -> dict:
    """给前端的状态摘要。绝不回传 hash。"""
    return {"lock_enabled": is_lock_enabled()}
