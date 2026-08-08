from __future__ import annotations

import datetime as dt

UTC = dt.timezone.utc


def utc_now() -> dt.datetime:
    """返回带 UTC 时区的当前时间。"""
    return dt.datetime.now(UTC)


def utc_now_naive() -> dt.datetime:
    """返回与历史 DateTime 字段兼容的 naive UTC 时间。"""
    return utc_now().replace(tzinfo=None)


def utc_now_iso() -> str:
    """返回 ISO8601 格式的 UTC 时间戳。"""
    return utc_now().isoformat()


def naive_utc_to_epoch(value: dt.datetime) -> float:
    """
    把库里的 naive UTC 时间转成 epoch 秒。

    **必须用这个函数,不要直接 `value.timestamp()`** —— naive datetime 会被
    Python 按**本地时区**解释,而库里存的是 UTC(见 utc_now_naive)。
    在 UTC+8 下,直接 .timestamp() 得到的 epoch 比真实时间早 8 小时,
    与 `datetime.now().timestamp()` 相减后凭空多出 8 小时"已过去的时间"。

    实际后果:主动关心的忙碌保护在数据库回落路径上永远判定为"很久没活跃",
    刚聊完重启就可能立刻打扰 —— 正是这个保护存在的意义所在。
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def local_hour_of(value: dt.datetime) -> int:
    """
    库里的 naive UTC 时间对应的**本地**小时(0-23)。

    作息统计要回答的是"这个人几点活跃",那是本地时间的概念;
    按 UTC 分桶会让整张作息表整体偏移时区差。
    """
    return dt.datetime.fromtimestamp(naive_utc_to_epoch(value)).hour
