from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship

from ..core.time_utils import utc_now_naive
from .base import Base

class ChatHistoryDB(Base):
    """
    聊天历史记录表
    """
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String(50), nullable=False) # 'user' or 'ai'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=utc_now_naive)
    
    # 异步消息队列支持
    # pending: 待处理 (刚入库)
    # processing: 正在处理中 (已被 Worker 捞取)
    # completed: 处理完成 (已生成回复或本身就是 AI 回复)
    # failed: 处理失败
    status = Column(String(20), default="completed", nullable=False) # 默认为 completed 兼容旧数据/AI消息
    
    # 异步任务关联
    task_id = Column(String(50), nullable=True)

    # 是否为主动关心消息(非用户提问触发)。
    # 加这个字段是为了让主动关心的效果**可被评估** —— 没有它就只能凭感觉调频率,
    # 而这个功能的参数恰恰被一路调激进过(每日 3→5、冷却 4h→2h、忙碌保护 5m→2m),
    # 每次改动都没有留下依据。有了标记就能算:主动消息发出后用户是否回复。
    is_proactive = Column(Boolean, default=False, nullable=False)

    # 会话 ID (用于多轮对话历史隔离)
    session_id = Column(String(50), nullable=True, index=True)

    # 关联
    user = relationship("UserDB", back_populates="chat_history")
    
    # 状态快照关联
    state_snapshot = Column(JSON, nullable=True) # 存储当时的 agent state 快照
    
    # 关联 WorkflowTraceDB (一对一)
    # 通过 relationship 定义，但通常我们在业务层通过 execution_id 关联
    # 这里为了简单，暂不建立强外键约束

class WorkflowTraceDB(Base):
    """
    工作流追踪数据库模型
    用于记录工作流执行过程中的节点输入输出，便于调试和审计。
    """
    __tablename__ = "workflow_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)
    user_id = Column(Integer, index=True, nullable=True) # 添加用户隔离审计
    execution_id = Column(String, index=True) # 本次请求/轮次的唯一 ID
    node_id = Column(String)
    input_data = Column(JSON)
    output_data = Column(JSON)
    timestamp = Column(String) # 存储为字符串 ISO 格式或类似格式
