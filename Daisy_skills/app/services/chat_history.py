from typing import List, Optional
import datetime
from sqlalchemy.orm import Session
from contextlib import contextmanager

from ..core.database import SessionLocal
from ..models.chat import ChatHistoryDB
from ..core.utils import group_chat_history_by_pairs

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

    def get_recent_history_limit(self, user_id: str, limit: int = 20, db: Optional[Session] = None) -> List[ChatHistoryDB]:
        """
        获取指定用户最近的 N 条记录，按时间正序返回。
        """
        with self._get_db(db) as session:
            # 先倒序取最近的，再反转
            query = session.query(ChatHistoryDB).filter(
                ChatHistoryDB.user_id == user_id
            )

            history = query.order_by(ChatHistoryDB.timestamp.desc()).limit(limit).all()
            return list(reversed(history))

    def get_recent_pairs(self, user_id: str, limit_pairs: int, days: int = 2, db: Optional[Session] = None) -> List[List[ChatHistoryDB]]:
        """
        获取最近的 N 对对话。
        """
        # 简化版：先获取最近的 100 条，然后分组，再取最后 N 对
        # 暂时忽略 days 参数，假设最近的记录都在近期
        raw_msgs = self.get_recent_history_limit(user_id, 100, db)
        
        # 分组
        grouped_pairs = group_chat_history_by_pairs(raw_msgs)
        
        # 截取
        if limit_pairs > 0 and grouped_pairs:
            return grouped_pairs[-limit_pairs:]
        
        return grouped_pairs if grouped_pairs else []
