"""
系统装配域

初始数据(init_data)、库表引导(schema_bootstrap)、会话管理(session)、
密钥校验(key_verification)、本地隐私锁(local_lock)、链路留痕(trace_store)。

进程启动与横切关注点。不含任何对话业务逻辑。

注意:这里**不做重导出**。调用方直接导入具体模块,
避免包名遮蔽同名子模块(参见 tasks/__init__.py 曾把 chat_task 从模块变成函数的教训)。
"""
