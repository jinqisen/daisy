import asyncio
import datetime
import json
from typing import Optional, Dict, Any
from app.core.redis import redis_client
from app.core.time_utils import naive_utc_to_epoch
import structlog

logger = structlog.get_logger()

class StateService:
    """
    状态服务
    负责维护用户在线状态、活跃时间、情感快照以及作息统计。
    """
    
    @staticmethod
    async def mark_user_online(user_id: str):
        """标记用户在线 (SSE 连接建立)"""
        key = f"user:{user_id}:online"
        # 5分钟过期，通过 SSE 心跳或重连刷新
        await redis_client.set(key, "1", ttl=300)
        
    @staticmethod
    async def mark_user_offline(user_id: str):
        """标记用户离线 (SSE 连接断开)"""
        key = f"user:{user_id}:online"
        await redis_client.delete(key)

    @staticmethod
    async def is_user_online(user_id: str) -> bool:
        """检查用户是否在线"""
        key = f"user:{user_id}:online"
        return await redis_client.exists(key) > 0
        
    @staticmethod
    async def get_online_users() -> list[str]:
        """获取所有在线用户 ID"""
        # 扫描 user:*:online
        # 生产环境建议使用 Set 维护在线列表以提高性能，这里简单使用 keys
        # 或者维护一个 user:online_set
        keys = await redis_client.keys("user:*:online")
        return [k.split(":")[1] for k in keys]

    @staticmethod
    async def get_all_known_users() -> list[str]:
        """
        获取所有已知用户 ID。

        以**数据库**为准,而不是扫 Redis 的 user:*:last_active。
        后者有两个致命问题,恰好把主动关心最有价值的场景废掉了:
          1. 嵌入模式下 Redis 是进程内 fakeredis,**重启即清空** ——
             实测重启后日志是 `found 0 known users: []`,库里明明有 24 条对话;
          2. 该 key 带 24h TTL,离开超过一天也会消失。
        两者合起来的效果是:**用户越久不联系,越不可能收到关心**,逻辑正好反了。

        数据库里有过对话记录,才是"这个用户存在"的持久事实。
        """
        def _query() -> list[str]:
            from app.core.database import SessionLocal
            from app.models import UserDB

            with SessionLocal() as db:
                return [u.username for u in db.query(UserDB.username).distinct()]

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _query)
        except Exception as e:
            logger.error(f"读取已知用户失败: {e}")
            return []

    @staticmethod
    async def resolve_user_db_id(user_id: str) -> Optional[int]:
        """
        用户名 -> users.id。

        主动关心这条链路上的 `user_id` 自始至终是**用户名字符串**
        (来自 get_all_known_users),而 chat_history.user_id 是指向 users.id 的
        **整数外键**。两者混用过一次:主动消息把用户名写进了整数列,
        SQLite 弱类型照单全收,结果那条消息既不属于任何用户、也永远不会
        出现在对话历史里 —— 连带我们为评估效果加的 is_proactive 标记一起失效。
        """
        def _query() -> Optional[int]:
            from app.core.database import SessionLocal
            from app.models import UserDB

            with SessionLocal() as db:
                row = (db.query(UserDB.id)
                         .filter(UserDB.username == user_id)
                         .first())
                return row[0] if row else None

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _query)
        except Exception as e:
            logger.error(f"解析用户 ID 失败: {e}")
            return None

    @staticmethod
    async def mark_user_active(user_id: str):
        """
        更新用户最后活跃时间 (发送消息时调用)。

        这里只写缓存 —— 真源是 chat_history 里那条消息本身。
        作息统计也不再单独累加(原先 hincrby 到 Redis 且无 TTL,
        而嵌入模式的 Redis 重启即空,统计永远攒不够可信样本)。
        """
        key = f"user:{user_id}:last_active"
        now_ts = datetime.datetime.now().timestamp()
        await redis_client.set(key, str(now_ts), ttl=86400) # 24h

    @staticmethod
    async def get_last_active_time(user_id: str) -> Optional[float]:
        """
        获取用户最后活跃时间戳。

        Redis 优先(热路径),但**必须能回落到数据库**:
        嵌入模式的 Redis 是进程内的,重启即空;该 key 还带 24h TTL。
        只读 Redis 的话,"用户离开多久了"这个主动关心最核心的判据,
        在重启后或离开超一天后会变成 None —— 而 None 会让忙碌保护直接放行,
        等于刚重启就可能立刻打扰。
        """
        key = f"user:{user_id}:last_active"
        ts = await redis_client.get(key)
        if ts:
            return float(ts)

        def _query() -> Optional[float]:
            from app.core.database import SessionLocal
            from app.models import ChatHistoryDB, UserDB

            with SessionLocal() as db:
                user = db.query(UserDB).filter(UserDB.username == user_id).first()
                if not user:
                    return None
                row = (db.query(ChatHistoryDB.timestamp)
                         .filter(ChatHistoryDB.user_id == user.id,
                                 ChatHistoryDB.role == "user")
                         .order_by(ChatHistoryDB.id.desc())
                         .first())
                # 库里是 naive UTC;直接 .timestamp() 会被当成本地时间,
                # 在 UTC+8 下凭空多算 8 小时"已过去的时间",忙碌保护随之失效。
                return naive_utc_to_epoch(row[0]) if row and row[0] else None

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _query)
        except Exception as e:
            logger.error(f"读取最后活跃时间失败: {e}")
            return None

    # 作息直方图的缓存有效期。丢了只是下次多查一次库,不影响正确性。
    ACTIVITY_CACHE_TTL = 3600
    # 参与统计的最近消息条数。有上界才不会随着历史增长越查越慢,
    # 同时也让作息反映**近期**习惯而不是一年前的作息。
    ACTIVITY_SAMPLE_LIMIT = 2000

    @staticmethod
    async def _activity_histogram(user_id: str) -> Dict[int, int]:
        """
        用户按小时的活跃直方图,来源是 chat_history —— **不是**独立累加的计数器。

        原实现每次发消息 hincrby 到 Redis 且不带 TTL。嵌入模式下 Redis 是进程内
        fakeredis,**重启即空**;而 get_activity_probability 又要求样本数 ≥10 才认为
        可信。两者合起来:统计永远攒不到 10 条,永远返回冷启动的保守值,
        「按作息挑时间」这个功能实际上从未生效过。

        改为从对话记录直接算:那本来就是同一个事实,而且是真持久的。
        Redis 只作带 TTL 的缓存,丢了自动重算。
        """
        key = f"user:{user_id}:activity_stats"
        cached = await redis_client.get(key)
        if cached:
            try:
                return {int(k): int(v) for k, v in json.loads(cached).items()}
            except Exception:
                pass  # 缓存坏了就当没有,下面重算

        def _query() -> Dict[int, int]:
            from app.core.database import SessionLocal
            from app.core.time_utils import local_hour_of
            from app.models import ChatHistoryDB, UserDB

            hist: Dict[int, int] = {}
            with SessionLocal() as db:
                user = db.query(UserDB).filter(UserDB.username == user_id).first()
                if not user:
                    return hist
                rows = (db.query(ChatHistoryDB.timestamp)
                          .filter(ChatHistoryDB.user_id == user.id,
                                  ChatHistoryDB.role == "user")
                          .order_by(ChatHistoryDB.id.desc())
                          .limit(StateService.ACTIVITY_SAMPLE_LIMIT)
                          .all())
                for (ts,) in rows:
                    if ts is None:
                        continue
                    h = local_hour_of(ts)
                    hist[h] = hist.get(h, 0) + 1
            return hist

        try:
            loop = asyncio.get_running_loop()
            hist = await loop.run_in_executor(None, _query)
        except Exception as e:
            logger.error(f"读取作息统计失败: {e}")
            return {}

        await redis_client.set(
            key,
            json.dumps({str(k): v for k, v in hist.items()}),
            ttl=StateService.ACTIVITY_CACHE_TTL,
        )
        return hist

    @staticmethod
    async def get_activity_probability(user_id: str, hour: int) -> float:
        """
        计算用户在指定小时的活跃概率
        Probability = (Hour_Count / Total_Count)
        """
        stats = await StateService._activity_histogram(user_id)

        if not stats:
            return 0.05 # 默认给予一个低概率而非 0，避免冷启动完全死锁

        total = sum(stats.values())
        if total < 10: # 样本太少，不可信
            return 0.1 # 返回一个保守值

        return stats.get(hour, 0) / total

    @staticmethod
    async def update_emotional_state(user_id: str, emotion_data: Dict[str, Any]):
        """
        更新用户情感状态快照
        emotion_data: { "label": "sadness", "score": 0.8, "summary": "..." }
        """
        key = f"user:{user_id}:last_emotion"
        # 存为 JSON
        data = {
            "label": emotion_data.get("label"),
            "score": emotion_data.get("score"),
            "summary": emotion_data.get("summary", ""),
            "timestamp": datetime.datetime.now().timestamp()
        }
        await redis_client.redis.set(key, json.dumps(data), ex=43200) # 12h 有效

    @staticmethod
    async def get_emotional_state(user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户最近的情感状态"""
        key = f"user:{user_id}:last_emotion"
        data = await redis_client.redis.get(key)
        if data:
            return json.loads(data)
        return None
