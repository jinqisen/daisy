from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from .base import Base

class LLMTraceDB(Base):
    """
    LLM 调用日志追踪
    """
    __tablename__ = "llm_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关联的用户 ID (如果可用)
    user_id = Column(Integer, nullable=True, index=True)
    
    # 智能体名称
    agent_name = Column(String, nullable=True)
    
    # 触发此调用的用户原始语句 (Response to which user sentence)
    trigger_message = Column(Text, nullable=True)
    
    # 触发此调用的用户消息 ID
    trigger_message_id = Column(Integer, nullable=True)
    
    # 发送给 LLM 的 System Prompt
    system_prompt = Column(Text, nullable=True)
    
    # 发送给 LLM 的 User Input (Prompt)
    user_input = Column(Text, nullable=True)
    
    # LLM 返回的响应
    response = Column(Text, nullable=True)
    
    # 错误信息 (如果有)
    error = Column(Text, nullable=True)
