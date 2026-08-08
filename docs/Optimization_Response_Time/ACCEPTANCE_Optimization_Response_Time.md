# ACCEPTANCE_Optimization_Response_Time

## 1. 变更摘要
已修改 `app/workflow/nodes/memory.py` 中的 `save_memory_and_log` 函数。
原本同步阻塞的 `memory_service.add_memory` 调用现在被封装在 `_background_tasks` 异步函数中，并通过 `asyncio.create_task` 提交执行。

## 2. 验证清单

### 2.1 代码逻辑验证
- [x] `save_memory_and_log` 不再 await `add_memory`。
- [x] `_background_tasks` 内部包含 `try-except` 捕获异常，防止 crash。
- [x] 使用 `asyncio.create_task` 实现 Fire-and-Forget。

### 2.2 部署验证
- [x] 重启 Docker 容器 `daisy_server_local_container` 以应用更改。

### 2.3 预期行为
1.  用户发送消息。
2.  服务器执行 Analysis -> Generation。
3.  服务器执行 Save (SQL部分)。
4.  服务器 **立即返回** HTTP 200 响应。
5.  Docker 日志中，在响应返回 **之后** (或几乎同时) 出现 "后台任务: 记忆存储完成" (或失败日志)。

## 3. 性能对比 (预估)
| 场景 | 优化前耗时 | 优化后耗时 (用户感知) | 收益 |
| :--- | :--- | :--- | :--- |
| 正常记忆存储 | Gen + 2s | Gen + 0s | -2s |
| 记忆存储重试/超时 | Gen + 22s | Gen + 0s | -22s |

## 4. 结论
优化已部署。请进行实际对话测试以验证响应速度的提升。
