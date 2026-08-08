"""
人格域

角色卡加载(character_card)、人格权重融合(fusion)、
对话策略选择(strategy)、情绪识别(emotion)。

决定 Daisy「是谁、此刻什么状态」;不接触存储细节。

注意:这里**不做重导出**。调用方直接导入具体模块,
避免包名遮蔽同名子模块(参见 tasks/__init__.py 曾把 chat_task 从模块变成函数的教训)。
"""
