from sqlalchemy import Column, Float, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from ..core.time_utils import utc_now_naive
from .base import Base


class MetricEventDB(Base):
    """
    指标事件的事实表(SLO 面板的真源)。

    这些量原先只累加在缓存里且**不带 TTL**。嵌入模式的缓存是进程内的、
    重启即空,于是累计量(总调用数/总 token/总成本)每次重启归零 ——
    面板永远只反映"本次运行",成本统计基本没有意义。

    一行 = 一个事件,聚合放到读取侧做。这样也顺带解决了原先"计数器与事实
    不一致"的隐患:没有计数器,只有事实。
    """

    __tablename__ = "metric_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 与库中其余时间字段一致:naive UTC(见 core/time_utils)
    timestamp = Column(DateTime, default=utc_now_naive, index=True)

    kind = Column(String(16), nullable=False, index=True)  # llm / router / e2e
    route = Column(String(32), nullable=True)              # FAST / STANDARD / DEEP
    model_name = Column(String(128), nullable=True)

    duration_ms = Column(Integer, nullable=True)   # router / e2e
    in_tokens = Column(Integer, nullable=True)     # llm
    out_tokens = Column(Integer, nullable=True)    # llm
    cost_usd = Column(Float, nullable=True)        # llm

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
