import datetime
import json
import structlog
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.core.time_utils import naive_utc_to_iso
from app.core.sse import build_protocol_event
from app.core.cache import redis_client
from app.services.proactive.state import StateService
from app.services.memory.chat_history import history_service
from app.models import UserDB
from app.core.database import SessionLocal
from app.agents.manager import AgentManager

logger = structlog.get_logger()

class ProactiveService:
    """
    主动对话服务
    核心逻辑：双轨门控 (Dual-Track Gatekeeper) + Agent 决策
    """
    
    # 硬性规则参数
    # 参数已移入 settings(见 core/config.py 的取值理由)。
    # 保留这几个类属性只为兼容既有引用,值一律来自配置。
    @staticmethod
    def _limits():
        from app.core.config import settings
        return settings

    @staticmethod
    def _in_quiet_hours(hour: int, cfg) -> bool:
        """
        是否处于静默时段。

        必须正确处理**跨午夜**的区间(如 23:00-08:00):
        直接写 start <= hour < end 在跨天时永远为假,静默时段等于没有。
        """
        start = cfg.PROACTIVE_QUIET_START_HOUR
        end = cfg.PROACTIVE_QUIET_END_HOUR
        if start == end:
            return False
        if start < end:                 # 不跨天,如 1:00-6:00
            return start <= hour < end
        return hour >= start or hour < end   # 跨天,如 23:00-8:00
    
    @staticmethod
    async def check_and_trigger(user_id: str):
        """
        核心入口：检查是否应该对指定用户发起主动对话
        由 Worker 任务调用
        """
        # 0. 基础检查：用户是否在线？
        is_online = await StateService.is_user_online(user_id)
        
        # 1. 收集状态
        now = datetime.datetime.now()
        current_hour = now.hour
        last_active = await StateService.get_last_active_time(user_id)
        
        logger.info(f"Checking proactive trigger for user {user_id} | Online: {is_online} | Last Active: {last_active}")

        if not is_online:
            # 即使不在线也继续，生成消息存库 (Future: Push Notification)
            logger.debug(f"User {user_id} is offline. Message will be stored if generated.")
        
        # 忙碌保护:刚聊完就又主动开口不像陪伴,像没话找话。
        cfg = ProactiveService._limits()
        busy_guard_sec = cfg.PROACTIVE_BUSY_GUARD_MINUTES * 60
        if last_active and (now.timestamp() - last_active < busy_guard_sec):
            logger.info(
                f"User {user_id} 刚活跃过(< {cfg.PROACTIVE_BUSY_GUARD_MINUTES} 分钟),跳过。"
            )
            return

        # 静默时段(硬性)。原先只靠"活跃概率 < 5%"判断,而冷启动默认返回 0.05,
        # `0.05 < 0.05` 为假 —— 新用户毫无静默保护,半夜也会被打扰。
        if ProactiveService._in_quiet_hours(current_hour, cfg):
            logger.info(
                f"处于静默时段({cfg.PROACTIVE_QUIET_START_HOUR}:00-"
                f"{cfg.PROACTIVE_QUIET_END_HOUR}:00),跳过。"
            )
            return

        emotional_state = await StateService.get_emotional_state(user_id)
        
        # 2. 双轨门控判定
        track = "routine"
        override = False
        
        # Track A: 情感急救
        if emotional_state:
            label = emotional_state.get("label", "").lower()
            score = emotional_state.get("score", 0)
            ts = emotional_state.get("timestamp", 0)
            
            # 检查是否过期 (12h)
            if (now.timestamp() - ts) < 43200:
                if label in ["sadness", "lonely", "grief", "anxiety"] and score > 0.6:
                    track = "emotional_aid"
                    override = True
                    logger.info(f"Emotional Override activated for {user_id}: {label} ({score})")

        # Track B: 常规陪伴 (作息检查)
        if not override:
            prob = await StateService.get_activity_probability(user_id, current_hour)
            # 如果活跃概率极低 (< 5%)，视为休息时间
            # FIX: 如果样本太少，StateService 返回 0.1，这里不会拦截
            if prob < 0.05:
                logger.info(f"Low activity probability ({prob:.2f}) for hour {current_hour}. Skipping.")
                return

        # 3. 冷却与频次检查
        # 这条链路上的 user_id 是**用户名**,而 chat_history 用的是整数外键,
        # 配额/冷却现在都查库,必须先换算一次。
        db_user_id = await StateService.resolve_user_db_id(user_id)
        if db_user_id is None:
            logger.warning(f"找不到用户 {user_id} 的数据库记录,跳过主动关心。")
            return

        daily_count = await ProactiveService._get_daily_count(db_user_id)
        # 情绪场景**不加配额**:负面情绪下说错话的代价远高于不说话,
        # override 的意义是让语气更克制(见 track 传递),而不是提高打扰频率。
        max_daily = cfg.PROACTIVE_MAX_DAILY

        if daily_count >= max_daily:
            logger.info(f"Daily limit reached ({daily_count}/{max_daily}). Skipping.")
            return

        last_proactive = await ProactiveService._get_last_proactive_time(db_user_id)
        cooldown = (cfg.PROACTIVE_EMOTION_COOLDOWN_HOURS if override
                    else cfg.PROACTIVE_COOLDOWN_HOURS)
        
        if last_proactive:
            elapsed_hours = (now.timestamp() - last_proactive) / 3600
            if elapsed_hours < cooldown:
                logger.info(f"In cooldown ({elapsed_hours:.2f}h < {cooldown}h). Skipping.")
                return

        # 4. Agent 决策与生成 (Refactored)
        db = SessionLocal()
        try:
            # 获取最近对话历史作为上下文
            history = history_service.get_recent_history_limit(user_id=user_id, limit=5, db=db)
            # 转换为文本格式
            history_str = "\n".join([f"{h.role}: {h.content}" for h in history])
            
            # 获取 Agent (这里目前默认获取 Daisy，未来可以根据 User 设置获取)
            agent_manager = AgentManager.get_instance()
            agent = agent_manager.get_agent("daisy")
            
            if not agent:
                logger.error("No active agent found for user.")
                return

            # 构造上下文。**必须带上角色卡** —— 主动关心和主对话得是同一个人,
            # 否则会出现"平时是静雯,主动开口变成另一个角色、甚至换种语言"。
            common = None
            try:
                from app.models import CommonSettingsDB
                row = (db.query(CommonSettingsDB)
                         .filter(CommonSettingsDB.user_id == db_user_id)
                         .first())
                common = row
            except Exception as e:
                logger.warning(f"读取角色设定失败,主动关心将使用默认人设: {e}")

            context = {
                "user_id": user_id,
                "history": history_str,
                "emotion": emotional_state if override else None,
                "time": now,
                "common_settings": common,
            }
            
            # 调用 Agent 决策
            decision = await agent.check_proactive_trigger(context)
            
            if decision and decision.get("should_act"):
                content = decision.get("content")
                logger.info(f"Proactive message generated for {user_id} by {agent.name}: {content}")
                
                # 5. 执行发送
                # 不再单独更新计数器 —— 落库的这条消息(is_proactive=True)
                # 本身就是配额与冷却的依据,不存在计数器与事实不一致的可能。
                await ProactiveService._send_message(
                    user_id, db_user_id, content, db, is_online
                )


            else:
                logger.info(f"Agent {agent.name} decided not to act. Reason: {decision.get('reason')}")
                
        finally:
            db.close()

    @staticmethod
    async def _send_message(user_id: str, db_user_id: int, content: str,
                            db: Session, is_online: bool = True):
        """
        发送消息到 SSE 频道并存库。

        `user_id` 是用户名(用于 SSE 频道),`db_user_id` 是整数外键(用于落库)——
        两者曾被混用:用户名被写进了整数外键列,那条消息于是不属于任何用户,
        既不出现在对话历史里,也无法用于统计。
        """
        from app.core.time_utils import utc_now_naive
        from app.models import ChatHistoryDB

        ai_msg = ChatHistoryDB(
            session_id=str(datetime.datetime.now().timestamp()), # 临时 session
            user_id=db_user_id,
            role="ai",
            content=content,
            # 表里其余行都是 naive UTC(utc_now_naive)。这里原先写的是
            # datetime.now() 即本地时间,在 UTC+8 下比同表其他行超前 8 小时,
            # 会把排序、"今天几条"、冷却判断一起算错。
            timestamp=utc_now_naive(),
            is_proactive=True,   # 留痕:用于评估主动关心的实际效果(回复率)
        )
        db.add(ai_msg)
        db.commit()
        
        # 2. 只有在线才推送 SSE
        if is_online:
            channel = f"chat:stream:{user_id}"
            msg_payload = build_protocol_event(
                event="proactive.message",
                data={
                    "content": content,
                    "timestamp": naive_utc_to_iso(ai_msg.timestamp),
                },
                legacy_type="proactive_message",
                content=content,
                timestamp=naive_utc_to_iso(ai_msg.timestamp),
            )
            await redis_client.redis.publish(channel, json.dumps(msg_payload))
            logger.info(f"Pushed proactive message to online user {user_id}")
        else:
            logger.info(f"Stored proactive message for offline user {user_id}")

    # --- 配额与冷却:真源是 chat_history,不是内存计数器 ---
    #
    # 原先每日配额与上次主动时间都存在 Redis 里。嵌入模式的 Redis 是进程内
    # fakeredis,**重启即空**,于是:
    #   - 每日上限重启即可绕过;
    #   - 冷却记录消失,刚重启就可能立刻打扰。
    # 而"打扰是不可逆的"(用户觉得烦就卸载,不会回来),这两条恰恰是最不该失效的。
    #
    # 现在直接数库里的主动消息 —— 消息本身就是"已经打扰过"这件事的事实记录,
    # 不存在计数器与事实不一致的可能。is_proactive 字段是上一轮为评估效果加的,
    # 这里正好复用,不需要新表。

    @staticmethod
    def _count_today_proactive(db_user_id: int, db: Session) -> int:
        from app.models import ChatHistoryDB

        # 库里是 naive UTC,"今天"也要按 UTC 起点算,否则跨时区会错一整天
        start = datetime.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return (db.query(ChatHistoryDB)
                  .filter(ChatHistoryDB.user_id == db_user_id,
                          ChatHistoryDB.is_proactive.is_(True),
                          ChatHistoryDB.timestamp >= start)
                  .count())

    @staticmethod
    async def _get_daily_count(db_user_id: Optional[int]) -> int:
        if db_user_id is None:
            # 解析不到用户就当作已达上限 —— 宁可不发,也不要在身份不明时打扰
            return 10 ** 6

        def _query() -> int:
            with SessionLocal() as db:
                return ProactiveService._count_today_proactive(db_user_id, db)

        try:
            import asyncio
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _query)
        except Exception as e:
            logger.error(f"读取今日主动消息数失败: {e}")
            return 10 ** 6   # 同上:读不到就不发

    @staticmethod
    async def _get_last_proactive_time(db_user_id: Optional[int]) -> Optional[float]:
        """
        上次主动开口的时间。同样以库为准 —— 冷却是"别刚说完又说"的保护,
        它必须跨重启有效,否则重启就等于把保护清零。
        """
        if db_user_id is None:
            return None

        def _query() -> Optional[float]:
            from app.core.time_utils import naive_utc_to_epoch
            from app.models import ChatHistoryDB

            with SessionLocal() as db:
                row = (db.query(ChatHistoryDB.timestamp)
                         .filter(ChatHistoryDB.user_id == db_user_id,
                                 ChatHistoryDB.is_proactive.is_(True))
                         .order_by(ChatHistoryDB.id.desc())
                         .first())
                return naive_utc_to_epoch(row[0]) if row and row[0] else None

        try:
            import asyncio
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _query)
        except Exception as e:
            logger.error(f"读取上次主动时间失败: {e}")
            # 读不到时返回"刚刚发过",让冷却拦住这一轮。
            # 返回 None 会被上游当作"从没发过"而直接放行 —— 那是不对称的错误方向。
            return datetime.datetime.now().timestamp()
