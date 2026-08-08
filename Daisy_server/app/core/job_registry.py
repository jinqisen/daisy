"""
后台任务注册表 —— 用注册反转依赖方向。

问题:嵌入模式的任务分发器住在 core/redis.py,却要 `from ..tasks.chat_task import ...`
才能找到任务函数。core 是最底层,反过来依赖 tasks 形成循环 —— 改任一侧都可能
从意想不到的方向回弹。

做法:core 只持有一张"名字 → 函数"的表,谁也不认识;tasks 在自己被导入时把
自己登记进来。依赖方向变成单向的 tasks → core。

注册发生在 app/tasks/__init__.py 导入时,而分发只会在应用运行期发生
(那时 tasks 早已被 worker / main 导入),所以不存在"还没注册就被调用"的窗口;
真出现未注册的名字也会明确报错,而不是静默返回 None。
"""

from typing import Callable, Dict, Optional

import structlog

logger = structlog.get_logger()

_REGISTRY: Dict[str, Callable] = {}


def register_job(name: str, fn: Callable) -> None:
    """登记一个后台任务。重复登记同名任务视为编程错误,直接报错而非静默覆盖。"""
    if name in _REGISTRY and _REGISTRY[name] is not fn:
        raise ValueError(f"Job '{name}' already registered with a different function")
    _REGISTRY[name] = fn


def resolve_job(name: str) -> Optional[Callable]:
    fn = _REGISTRY.get(name)
    if fn is None:
        logger.error(
            f"未注册的后台任务 '{name}';已注册:{sorted(_REGISTRY)}。"
            f"通常是 app.tasks 尚未被导入所致。"
        )
    return fn


def registered_jobs() -> Dict[str, Callable]:
    return dict(_REGISTRY)
