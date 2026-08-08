"""
测试会话级的隔离设置。

**必须在任何 app 模块被导入之前生效** —— `core/database.py` 在模块导入时就读
`DAISY_DB_PATH` 并据此建好 engine。pytest 会先导入 conftest.py,所以这里设置
环境变量是唯一可靠的时机;放进 fixture 就晚了。

为什么需要:测试套件里有真实启动应用的用例(启动烟测跑完整 lifespan),
它会把指标 sink、轨迹 sink 等**进程级全局实现**装到真实数据库上。
之后任何触发埋点的测试都会往开发机的库里写行 —— 实测每跑一次污染 2 行。

这与当初"测试往仓库里的 server_config.json 写真值、密钥最终随 .dmg 分发出去"
是同一类问题:**测试的副作用逃出了测试**。那次的代价是一个真实密钥泄漏,
所以这里宁可一刀切:测试永远不碰真实数据。
"""

import os
import tempfile

_TEST_DB_DIR = tempfile.mkdtemp(prefix="daisy-tests-")

# setdefault:允许外部显式指定(比如要针对某个真实库复现问题时)
os.environ.setdefault("DAISY_DB_PATH", os.path.join(_TEST_DB_DIR, "test.db"))
os.environ.setdefault("DAISY_DATA_DIR", _TEST_DB_DIR)
