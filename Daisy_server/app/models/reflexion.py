from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from .base import Base

class ReflexionLogDB(Base):
    """
    异步反思日志
    记录每轮对话的反思结果和改进建议
    """
    __tablename__ = "reflexion_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    user_id = Column(Integer, nullable=False, index=True)
    session_id = Column(String, nullable=True)
    
    # 原始对话摘要
    user_input = Column(Text, nullable=True)
    agent_response = Column(Text, nullable=True)
    
    # 反思结果
    critique = Column(Text, nullable=True)  # 批评/分析
    improvement_plan = Column(Text, nullable=True) # 改进计划
    
    # 状态
    status = Column(String, default="pending") # pending, processed
    
    # 结构化数据 (JSON)
    metrics = Column(JSON, nullable=True) # 评分或其他指标
