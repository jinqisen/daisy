"""
学习域

Reflexion 评分与补丁(reflexion/、reflexion_system)、
强化学习采样与数据集(rl_agent、rl_dataset)。

从已发生的对话里回捞改进信号。全部是 enhancement 级:
失败只影响后续优化质量,不能阻断当前对话。

注意:这里**不做重导出**。调用方直接导入具体模块,
避免包名遮蔽同名子模块(参见 tasks/__init__.py 曾把 chat_task 从模块变成函数的教训)。
"""
