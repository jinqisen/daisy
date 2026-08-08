from typing import Any, Dict, List, Optional
import datetime
from sqlalchemy.orm import Session
from contextlib import contextmanager

from app.core.database import SessionLocal
from app.core.time_utils import utc_now_naive
from app.models import ChatHistoryDB, WorkflowTraceDB, ReflexionLogDB
from app.core.utils import group_chat_history_by_pairs

class ChatHistoryService:
    """
    统一的聊天记录查询服务。
    封装所有对 ChatHistoryDB 的访问逻辑。
    """

    @contextmanager
    def _get_db(self, db: Optional[Session] = None):
        """Helper to use provided session or create a new one"""
        if db:
            yield db
        else:
            with SessionLocal() as session:
                yield session

    def get_all_history(self, user_id: str, db: Optional[Session] = None) -> List[ChatHistoryDB]:
        """获取所有历史记录"""
        with self._get_db(db) as session:
            return session.query(ChatHistoryDB).filter(
                ChatHistoryDB.user_id == user_id
            ).order_by(ChatHistoryDB.id.asc()).all()

    def get_recent_history_by_time(self, user_id: str, days: int = 2, db: Optional[Session] = None, exclude_statuses: Optional[List[str]] = None) -> List[ChatHistoryDB]:
        """
        获取指定用户最近 N 天的历史记录，按时间正序排列。
        """
        with self._get_db(db) as session:
            # Use UTC to match DB default
            cutoff_time = utc_now_naive() - datetime.timedelta(days=days)

            query = session.query(ChatHistoryDB).filter(
                ChatHistoryDB.user_id == user_id,
                ChatHistoryDB.timestamp >= cutoff_time
            )

            if exclude_statuses:
                query = query.filter(ChatHistoryDB.status.notin_(exclude_statuses))

            return query.order_by(ChatHistoryDB.timestamp.asc()).all()

    def get_recent_history_limit(
        self,
        user_id: str,
        limit: int = 20,
        db: Optional[Session] = None,
        exclude_statuses: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> List[ChatHistoryDB]:
        """
        获取指定用户最近的 N 条记录，按时间正序返回。
        """
        with self._get_db(db) as session:
            # 先倒序取最近的，再反转
            query = session.query(ChatHistoryDB).filter(
                ChatHistoryDB.user_id == user_id
            )

            if session_id:
                query = query.filter(ChatHistoryDB.session_id == session_id)

            if exclude_statuses:
                query = query.filter(ChatHistoryDB.status.notin_(exclude_statuses))

            history = query.order_by(ChatHistoryDB.timestamp.desc()).limit(limit).all()
            return list(reversed(history))

    def get_recent_pairs(self, user_id: str, limit_pairs: int, days: int = 2, db: Optional[Session] = None, exclude_statuses: Optional[List[str]] = None) -> List[List[ChatHistoryDB]]:
        """
        获取最近的 N 对对话。
        首先按时间范围筛选，然后分组，最后取最近的 limit_pairs 对。
        """
        # 1. 获取基础数据 (按时间范围，避免全表扫描)
        # 注意：这里直接调用 self.get_recent_history_by_time，传递 db
        raw_msgs = self.get_recent_history_by_time(user_id, days, db, exclude_statuses=exclude_statuses)
        
        # 2. 分组
        grouped_pairs = group_chat_history_by_pairs(raw_msgs)
        
        # 3. 截取
        if limit_pairs > 0 and grouped_pairs:
            return grouped_pairs[-limit_pairs:]
        
        return grouped_pairs if grouped_pairs else []

    def get_recent_pairs_from_all(self, user_id: str, limit_pairs: int, db: Optional[Session] = None) -> List[List[ChatHistoryDB]]:
        """从所有历史中获取最近的 N 对 (不限制时间)"""
        # 原始逻辑行为：获取所有历史以确保分组正确
        all_msgs = self.get_all_history(user_id, db)
        grouped_pairs = group_chat_history_by_pairs(all_msgs)
        
        if limit_pairs > 0 and grouped_pairs:
            return grouped_pairs[-limit_pairs:]
        return grouped_pairs if grouped_pairs else []

    def get_user_messages_by_session(self, session_id: str, limit: int = 10, db: Optional[Session] = None) -> List[str]:
        """获取指定 Session 最近的用户消息内容"""
        with self._get_db(db) as session:
            history = session.query(ChatHistoryDB).filter(
                ChatHistoryDB.session_id == session_id,
                ChatHistoryDB.role == "user"
            ).order_by(ChatHistoryDB.id.desc()).limit(limit).all()
            
            if history:
                return [h.content for h in reversed(history)]
            return []

    def get_last_message_id(self, user_id: str, db: Optional[Session] = None) -> Optional[int]:
        """获取用户最后一条消息的 ID"""
        with self._get_db(db) as session:
            msg = session.query(ChatHistoryDB).filter(
                ChatHistoryDB.user_id == user_id
            ).order_by(ChatHistoryDB.id.desc()).first()
            return msg.id if msg else None

    def get_last_message(self, user_id: str, db: Optional[Session] = None) -> Optional[ChatHistoryDB]:
        """获取用户最后一条消息对象"""
        with self._get_db(db) as session:
            return session.query(ChatHistoryDB).filter(
                ChatHistoryDB.user_id == user_id
            ).order_by(ChatHistoryDB.id.desc()).first()

    def get_message_by_id(self, message_id: int, db: Optional[Session] = None) -> Optional[ChatHistoryDB]:
        """通过 ID 获取消息"""
        with self._get_db(db) as session:
            return session.query(ChatHistoryDB).filter(ChatHistoryDB.id == message_id).first()
            
    def get_session_history(self, user_id: str, session_id: str, db: Optional[Session] = None, exclude_statuses: Optional[List[str]] = None) -> List[ChatHistoryDB]:
        """获取指定 Session 的所有消息 (用于增量 Summarize)"""
        with self._get_db(db) as session:
            query = session.query(ChatHistoryDB).filter(
                ChatHistoryDB.user_id == user_id,
                ChatHistoryDB.session_id == session_id
            )
            
            if exclude_statuses:
                query = query.filter(ChatHistoryDB.status.notin_(exclude_statuses))
                
            return query.order_by(ChatHistoryDB.timestamp.asc()).all()

    def get_session_history_after_message(
        self,
        user_id: str,
        session_id: str,
        after_message_id: int,
        db: Optional[Session] = None,
        exclude_statuses: Optional[List[str]] = None,
    ) -> List[ChatHistoryDB]:
        """获取指定 Session 中某条消息之后的消息，按时间正序返回。"""
        with self._get_db(db) as session:
            query = session.query(ChatHistoryDB).filter(
                ChatHistoryDB.user_id == user_id,
                ChatHistoryDB.session_id == session_id,
                ChatHistoryDB.id > after_message_id,
            )

            if exclude_statuses:
                query = query.filter(ChatHistoryDB.status.notin_(exclude_statuses))

            return query.order_by(ChatHistoryDB.timestamp.asc()).all()

    def persist_workflow_trace(
        self,
        session_id: str,
        user_id: Optional[int],
        execution_id: Optional[str],
        node_id: str,
        input_data: Any,
        output_data: Any,
        timestamp: str,
        db: Optional[Session] = None,
    ) -> None:
        with self._get_db(db) as session:
            trace_entry = WorkflowTraceDB(
                session_id=session_id,
                user_id=str(user_id) if user_id is not None else None,
                execution_id=execution_id,
                node_id=node_id,
                input_data=input_data,
                output_data=output_data,
                timestamp=timestamp,
            )
            session.add(trace_entry)
            session.commit()

    def load_workflow_trace_map(self, execution_id: Optional[str], db: Optional[Session] = None) -> Dict[str, Dict[str, Any]]:
        if not execution_id:
            return {}
        with self._get_db(db) as session:
            traces = session.query(WorkflowTraceDB).filter(WorkflowTraceDB.execution_id == execution_id).all()
            return {
                t.node_id: {"input": t.input_data, "output": t.output_data, "timestamp": t.timestamp}
                for t in traces
            }

    def save_user_message(
        self,
        *,
        session_id: str,
        user_id: int,
        content: str,
        status: str = "completed",
        state_snapshot: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime.datetime] = None,
        db: Optional[Session] = None,
    ) -> int:
        with self._get_db(db) as session:
            user_msg = ChatHistoryDB(
                session_id=session_id,
                user_id=user_id,
                role="user",
                content=content,
                status=status,
                state_snapshot=state_snapshot,
                timestamp=timestamp or utc_now_naive(),
            )
            session.add(user_msg)
            session.flush()
            msg_id = user_msg.id
            session.commit()
            return msg_id

    def get_message_with_response(self, message_id: int, user_id: int, db: Optional[Session] = None) -> tuple[Optional[ChatHistoryDB], Optional[ChatHistoryDB]]:
        """
        获取指定消息及其后续的 AI 回复 (如果是用户消息)。
        Returns: (target_message, ai_response_message)
        """
        with self._get_db(db) as session:
            msg = session.query(ChatHistoryDB).filter(
                ChatHistoryDB.id == message_id,
                ChatHistoryDB.user_id == user_id
            ).first()
            
            if not msg:
                return None, None
                
            ai_response = None
            if msg.role == "user":
                ai_response = session.query(ChatHistoryDB).filter(
                    ChatHistoryDB.session_id == msg.session_id,
                    ChatHistoryDB.user_id == user_id,
                    ChatHistoryDB.id > msg.id,
                ChatHistoryDB.role == "ai"
            ).order_by(ChatHistoryDB.id.asc()).first()
        return msg, ai_response

    def save_reflexion_log(self, user_id: int, session_id: str, user_input: str, agent_response: str, critique: str, improvement_plan: str, metrics: Dict, status: str = "processed", db: Optional[Session] = None):
        """保存反思日志 (Legacy: 直接保存 processed 状态)"""
        with self._get_db(db) as session:
            log = ReflexionLogDB(
                user_id=user_id,
                session_id=session_id,
                user_input=user_input,
                agent_response=agent_response,
                critique=critique,
                improvement_plan=improvement_plan,
                metrics=metrics,
                status=status
            )
            session.add(log)
            session.commit()
            return log.id

    def create_pending_reflexion_log(self, user_id: int, session_id: str, user_input: str, agent_response: str, metrics: Dict, db: Optional[Session] = None) -> int:
        """创建待处理的反思日志 (仅包含 Q_I)"""
        with self._get_db(db) as session:
            log = ReflexionLogDB(
                user_id=user_id,
                session_id=session_id,
                user_input=user_input,
                agent_response=agent_response,
                metrics=metrics,
                status="pending"
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            return log.id

    def update_reflexion_log(self, log_id: int, critique: str, improvement_plan: str, metrics: Dict, status: str = "processed", db: Optional[Session] = None):
        """更新反思日志 (补充 E_U, D_R, S_total)"""
        with self._get_db(db) as session:
            log = session.query(ReflexionLogDB).filter(ReflexionLogDB.id == log_id).first()
            if log:
                log.critique = critique
                log.improvement_plan = improvement_plan
                log.metrics = metrics
                log.status = status
                session.commit()

    def get_traces(self, session_id: str, execution_id: Optional[str] = None, user_id: Optional[int] = None, db: Optional[Session] = None) -> List[WorkflowTraceDB]:
        """获取工作流追踪记录"""
        with self._get_db(db) as session:
            query = session.query(WorkflowTraceDB).filter(WorkflowTraceDB.session_id == session_id)
            if execution_id:
                query = query.filter(WorkflowTraceDB.execution_id == execution_id)
            if user_id is not None:
                query = query.filter(WorkflowTraceDB.user_id == user_id)
            return query.order_by(WorkflowTraceDB.timestamp.asc()).all()

    def save_ai_message(
        self,
        *,
        session_id: str,
        user_id: int,
        content: str,
        state_snapshot: Dict[str, Any],
        timestamp: Optional[datetime.datetime] = None,
        db: Optional[Session] = None,
    ) -> int:
        with self._get_db(db) as session:
            ai_msg = ChatHistoryDB(
                session_id=session_id,
                user_id=user_id,
                role="ai",
                content=content,
                state_snapshot=state_snapshot,
                timestamp=timestamp or utc_now_naive(),
            )
            session.add(ai_msg)
            session.flush()
            ai_id = ai_msg.id
            session.commit()
            return ai_id

# 全局实例
history_service = ChatHistoryService()
