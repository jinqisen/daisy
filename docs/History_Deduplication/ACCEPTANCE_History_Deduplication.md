# 验收报告：LLM 历史记录去重

## 1. 问题复盘
在异步任务模式下，Worker 处理用户消息时：
1.  用户消息已入库 (Status: `pending` -> `processing`)。
2.  Worker 将该消息内容作为 `current_input` 传给 LLM。
3.  Worker 同时调用 `TopicAgent` 获取历史记录。
4.  **原逻辑**: `get_recent_pairs` 包含所有消息，因此 `processing` 状态的当前消息也被纳入历史记录。
5.  **结果**: LLM 收到双份输入（一份在 Context 中，一份在 User Input 中）。

## 2. 解决方案实施
### 2.1 修改 `ChatHistoryService`
*   增加 `exclude_statuses` 参数。
*   在 `get_recent_history_by_time` 和 `get_recent_pairs` 中应用 SQL 过滤：
    ```python
    if exclude_statuses:
        query = query.filter(ChatHistoryDB.status.notin_(exclude_statuses))
    ```

### 2.2 修改 `TopicAnalysisAgent`
*   调用 `get_recent_pairs` 时显式排除 `pending` 和 `processing` 消息：
    ```python
    recent_pairs = history_service.get_recent_pairs(
        user_id, 
        limit, 
        exclude_statuses=["pending", "processing"]
    )
    ```

## 3. 效果验证
*   **LLM Context**: 现在的历史记录将只包含之前的对话，不包含当前正在处理的这轮消息。
*   **Current Input**: 当前消息仅作为 User Input 传入。
*   **API 兼容性**: 前端调用的 `/api/chat/history` 接口不受影响（默认参数为 `None`，依然返回所有状态的消息）。

## 4. 部署
*   后端镜像已重新构建: `daisy_server_local`。
