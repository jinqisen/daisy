# 任务：历史记录同步状态调整 (ALIGNMENT)

## 1. 背景与问题
当前架构采用了“消息入库 -> 异步任务队列 -> SSE 推送”的模式。这意味着用户消息在后端存在 `pending` (待处理) 和 `processing` (处理中) 等中间状态。

**目前存在的问题：**
1.  **状态丢失**：`/api/chat/history` 接口返回的 `HistoryItem` 模型不包含 `status` 字段。前端加载历史记录时，无法得知消息是否仍在处理中。
2.  **交互断层**：用户发送消息后若刷新页面，前端会重新加载历史记录。由于缺乏状态信息，前端可能认为该条用户消息已“完成”，不再显示“思考中/加载中”的 UI 状态，导致用户误以为 AI 没有响应。

## 2. 需求分析
为了在页面刷新或重新连接后能够无缝恢复对话状态，我们需要：
1.  **后端**：`/api/chat/history` 必须透传数据库中的消息 `status`。
2.  **前端**：`useChat` 加载历史记录时，需要根据最后一条消息的状态（或角色）来智能恢复 `loading` 状态。

## 3. 方案设计

### 3.1 后端调整
*   **文件**: `Daisy_server/app/api/server.py`
*   **修改**: 更新 `HistoryItem` Pydantic 模型，增加 `status` 字段。
*   **逻辑**: 确保 `get_chat_history` 查询时能正确映射该字段。

### 3.2 前端调整
*   **文件**: `Daisy_front/src/hooks/useChat.ts`
*   **修改**:
    *   在解析历史记录时，读取 `status` 字段。
    *   **智能恢复 Loading**: 在 `loadHistory` 完成后，检查最后一条消息。
        *   如果最后一条是 **用户消息** (且状态不是 `failed/error`) -> 设置 `setLoading(true)`。
        *   或者，如果后端显式返回了 `pending/processing` 状态 -> 设置 `setLoading(true)`。
    *   这样，UI 会自动展示 "AI 正在输入..." 或加载动画，直到 SSE 推送真正的 AI 回复。

## 4. 待确认点
*   **Q**: 数据库中 `ChatHistoryDB` 的 `status` 字段默认值是什么？
    *   **A**: 代码显示默认为 `completed`，但新插入的用户消息是 `pending`。
*   **Q**: 前端是否需要新的 UI 状态？
    *   **A**: 暂时不需要。复用现有的 `loading` 状态即可满足需求（即显示“对方正在输入”或底部的 Loading Bar）。

## 5. 执行计划
1.  修改后端 `HistoryItem` 模型。
2.  修改前端 `useChat.ts` 的 `loadHistory` 逻辑。
3.  验证：发送消息 -> 立即刷新页面 -> 确认 UI 是否显示 Loading -> 等待 SSE 推送结果。
