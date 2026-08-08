"""
后台任务包。

导入本包即完成任务注册 —— 依赖方向由此保持单向(tasks → core)。
此前是 core/redis.py 反过来 import tasks 来查找任务函数,构成循环依赖。

注意:这里刻意**只导入模块、不把函数名绑到包上**。
若写成 `from .chat_task import chat_task`,包属性 `app.tasks.chat_task` 会从
「模块」变成「函数」,任何 `monkeypatch.setattr(chat_task, "SessionLocal", ...)`
之类按模块寻址的代码都会失效(实测打断了两个测试)。
"""

from . import chat_task as _chat_task
from . import proactive_task as _proactive_task
from ..core.job_registry import register_job

register_job("chat_task", _chat_task.chat_task)
register_job("proactive_check_task", _proactive_task.proactive_check_task)
register_job("trigger_proactive_checks", _proactive_task.trigger_proactive_checks)
