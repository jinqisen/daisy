"""
工作流节点的能力分级契约。

为什么需要:一次真实事故 —— 用户没配可选的搜索密钥,`tool_check` 抛异常,
异常一路冒泡打死整个 chat_task,消息永久卡在 pending,之后每次发送都会重放它。
**一个可选的增强功能,让用户完全说不了话。**

根因不是那处 try/except 写漏了,而是**没有契约**:没人规定过哪些节点是对话的
必要条件、哪些只是锦上添花。缺了契约,每个节点的错误处理都靠作者当时的判断,
迟早会漏。

契约:
  ESSENTIAL   —— 缺了它对话就没有意义(情感分析、最终生成、落库)。
                 失败应向上传播,由任务层统一处理并如实告知用户。
  ENHANCEMENT —— 让回复更好,但没有也能对话(工具检索、长期记忆、话题总结、
                 画像、人格融合)。失败**必须**降级为空结果,绝不中断对话。

用 @enhancement 装饰的节点自带兜底,不依赖作者记得写 try/except。
"""

from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict

import structlog

logger = structlog.get_logger()


class Capability(str, Enum):
    ESSENTIAL = "essential"
    ENHANCEMENT = "enhancement"


# 节点名 → 等级。测试据此校验每个注册进图的节点都已声明(见 tests/test_capability_contract.py)
_LEVELS: Dict[str, Capability] = {}


def _declare(name: str, level: Capability) -> None:
    _LEVELS[name] = level


def capability_of(name: str) -> Capability | None:
    return _LEVELS.get(name)


def declared_capabilities() -> Dict[str, Capability]:
    return dict(_LEVELS)


def essential(fn: Callable) -> Callable:
    """
    标记为必需节点。不改变行为 —— 失败照常向上传播,由任务层统一兜底。
    存在的意义是**显式声明**:读代码的人一眼看出这里失败会中断对话。
    """
    _declare(fn.__name__, Capability.ESSENTIAL)
    fn._capability = Capability.ESSENTIAL
    return fn


def enhancement(*, fallback: Dict[str, Any] | Callable[[], Dict[str, Any]] | None = None):
    """
    标记为增强节点,并**强制**兜底:任何异常都转为降级返回,不向上传播。

    fallback 给出降级时应写入状态的键值(如 {"tool_results": {}})。
    必须显式给出而非留空:下游汇聚可能在等这个键,悄悄不写会让它一直等下去 ——
    那是另一种形式的中断。
    """
    def deco(fn: Callable) -> Callable:
        _declare(fn.__name__, Capability.ENHANCEMENT)

        def _fallback_value() -> Dict[str, Any]:
            if callable(fallback):
                return fallback()
            return dict(fallback or {})

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                logger.warning(
                    f"增强节点 '{fn.__name__}' 失败,已降级继续对话: {e}",
                    node=fn.__name__,
                )
                return _fallback_value()

        wrapper._capability = Capability.ENHANCEMENT
        wrapper._fallback = fallback
        return wrapper

    return deco
