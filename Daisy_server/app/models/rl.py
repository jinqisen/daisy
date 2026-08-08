from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String

from .base import Base


class RLSampleDB(Base):
    """
    (context, action, reward) 样本 —— contextual bandit / RL 的训练与离线评估数据。

    每条对应一次"人格策略选择 + 其事后得到的用户满意度":
      context  当时的情绪/投入度/关系阶段(低维,避免小样本过拟合)
      action   实际选用的人格原型
      reward   Reflexion 算出的 S 分数(下一轮用户反应才能结算)
      policy   产生该样本的策略名 —— 离线策略评估(OPE)做重要性加权时必需

    注:样本只记录、不影响线上决策。是否启用 bandit 由离线评估结果决定。
    """

    __tablename__ = "rl_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True)
    session_id = Column(String, index=True)

    context_json = Column(JSON)          # {"emo_joy": 0.1, ..., "engagement": 0.7, "relationship": 0.5}
    action = Column(String, index=True)  # 六种人格原型之一
    action_weights_json = Column(JSON)   # 策略输出的完整权重分布(用于 OPE 的倾向性得分)
    policy = Column(String, index=True)  # "llm" | "rl" | "random" ...

    reward = Column(Float)
    # D_R 不可信时 S 会剔除该分量并重新归一化;此标记供训练时筛选同质样本
    reward_reliable = Column(Boolean, default=True)
    metrics_json = Column(JSON)          # 完整 Q_I/E_U/D_R 明细,便于事后换奖励定义重算

    timestamp = Column(DateTime, index=True)
