from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base

class ChatHistoryDB(Base):
    """
    Chat History Table
    """
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String(50), nullable=False) # 'user' or 'ai'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Async Queue Status
    status = Column(String(20), default="completed", nullable=False)
    task_id = Column(String(50), nullable=True)

    # Session ID
    session_id = Column(String(50), nullable=True, index=True)

    # Relationships
    user = relationship("UserDB", back_populates="chat_history")
    
    # State Snapshot
    state_snapshot = Column(JSON, nullable=True)
    
class WorkflowTraceDB(Base):
    """
    Workflow Trace Database Model
    """
    __tablename__ = "workflow_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)
    user_id = Column(Integer, index=True, nullable=True)
    execution_id = Column(String, index=True)
    node_id = Column(String)
    input_data = Column(JSON)
    output_data = Column(JSON)
    timestamp = Column(String)
