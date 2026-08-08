"""
LLM 结构化输出的容错解析。

为什么需要:模型生成长嵌套中文 JSON 时会稳定地出错,实测两类:
  - 明确要求"不要 Markdown"仍加 ```json 围栏;
  - 字符串内含中文弯引号「‘’」时,用中文右引号 ” 或 ASCII 单引号去闭合 JSON 字符串。
这不是 prompt 能可靠消除的 —— 实测加 response_format={"type":"json_object"}
后两个毛病依旧。角色卡这种一次性大对象(2000~3000 tokens)命中率尤其低。

策略:先按标准 JSON 解析(绝大多数情况直接通过,零开销),失败再走修复。
"""

import json
import re
from typing import Any

import structlog

logger = structlog.get_logger()

_FENCE_HEAD = re.compile(r"^```(?:json|JSON)?\s*")
_FENCE_TAIL = re.compile(r"\s*```$")


def strip_code_fence(text: str) -> str:
    """去掉 Markdown 代码围栏。用正则而非固定切片,以兼容 ``` / ```json / ```JSON。"""
    return _FENCE_TAIL.sub("", _FENCE_HEAD.sub("", (text or "").strip()))


def parse_llm_json(text: str) -> Any:
    """
    解析 LLM 返回的 JSON,必要时修复。

    抛 ValueError 而不是返回 None —— 调用方需要区分"模型没返回"和"返回了但没法用"。
    """
    cleaned = strip_code_fence(text)
    if not cleaned:
        raise ValueError("LLM returned empty content")

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        first_error = e

    try:
        import json_repair
    except ImportError:
        raise ValueError(f"Malformed JSON from LLM and json_repair unavailable: {first_error}")

    repaired = json_repair.loads(cleaned)
    # json_repair 修不动时会返回空串/空对象,那和解析失败没区别,不能当成功
    if repaired in ("", None) or (isinstance(repaired, (dict, list)) and not repaired):
        raise ValueError(f"Malformed JSON from LLM, repair produced nothing: {first_error}")

    logger.warning(
        "Repaired malformed JSON from LLM",
        error=str(first_error),
        length=len(cleaned),
    )
    return repaired
