# 任务：LLM 上下文历史记录去重 (ALIGNMENT)

## 1. 问题描述
当前后端采用异步任务处理模式：
1.  用户发送消息 -> 存入 DB (Status='pending')。
2.  Worker 获取消息 -> 更新 Status='processing' -> 合并内容作为 `current_input`。
3.  Worker 调用 `TopicAgent` 构建 LLM 上下文。
4.  `TopicAgent` 调用 `history_service.get_recent_pairs` 获取历史记录。

**冲突点**：
`get_recent_pairs` 默认获取所有历史记录（包括刚刚入库且正在处理的 `processing` 消息）。
导致 LLM 的 Prompt 中同时出现：
*   **History 部分**: 包含该条用户消息。
*   **User Input 部分**: 再次包含该条用户消息。

这将导致重复语义，甚至让 LLM 困惑（"用户为什么把刚才说的话又说了一遍？"）。

## 2. 解决方案
调整历史记录获取逻辑，在构建 LLM 上下文时，**显式排除**当前正在处理的消息（即状态为 `pending` 或 `processing` 的消息）。

## 3. 修改计划

### 3.1 修改 `ChatHistoryService`
*   **文件**: `Daisy_server/app/services/chat_history.py`
*   **变更**:
    *   `get_recent_history_by_time` 增加参数 `exclude_statuses: List[str] = None`。
    *   `get_recent_pairs` 增加参数 `exclude_statuses: List[str] = None`。
    *   在 SQL 查询中应用 `filter(ChatHistoryDB.status.notin_(exclude_statuses))`。

### 3.2 修改 `TopicAnalysisAgent`
*   **文件**: `Daisy_server/app/services/topic_agent.py`
*   **变更**:
    *   在 `_sync_process` 方法中调用 `get_recent_pairs` 时，传入 `exclude_statuses=["pending", "processing"]`。

## 4. 验证
*   检查代码逻辑确保 `status` 字段被正确过滤。
*   确保常规 API (`/api/chat/history`) 不受影响（不传该参数，默认返回所有）。
