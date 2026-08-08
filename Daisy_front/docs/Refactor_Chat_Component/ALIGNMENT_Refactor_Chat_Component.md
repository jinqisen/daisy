# 任务：重构对话组件 (ChatInterface) 对齐文档

## 1. 现状分析与问题诊断

### 1.1 核心问题
当前 `ChatInterface.tsx` 组件采用了 **SSE (Server-Sent Events) 推送** 与 **定时轮询 (Polling)** 混合的模式，导致了以下严重问题：

1.  **状态竞争与重复消息**：轮询获取的历史记录与 SSE 推送的实时消息在前端进行“启发式合并”（Smart Merge Strategy），依赖内容匹配而非唯一 ID。这导致：
    *   消息重复显示。
    *   本地临时消息无法正确更新为后端持久化消息。
    *   “获取AI恢复失败”等误报，实际上是状态同步逻辑混乱导致的。
2.  **ID 管理混乱**：
    *   前端发送消息生成临时 ID (`Date.now()`)。
    *   后端接收消息生成数据库 ID。
    *   SSE 推送时前端又生成一个新的临时 ID。
    *   三者之间缺乏明确的映射机制，导致无法精确更新状态。
3.  **代码复杂度过高**：组件内部混合了 UI 渲染、复杂的数据合并逻辑、SSE 连接管理、轮询定时器，难以维护和调试。
4.  **用户体验不佳**：发送消息后状态反馈迟钝，或出现空对话框（已修复但根源未除），必须刷新页面才能看到完整正确的记录。

### 1.2 现有架构约束
*   **前端**：React + Ant Design。
*   **后端**：FastAPI + Redis (PubSub) + ARQ (Async Tasks)。
*   **通信**：
    *   `POST /api/chat`: 异步任务入队。
    *   `GET /api/chat/stream`: SSE 实时推送。
    *   `GET /api/chat/history`: 历史记录查询。

## 2. 重构目标

### 2.1 核心目标
建立一个 **稳定、可预测、单向数据流** 的消息管理机制。

### 2.2 具体指标
*   **单一数据源**：以本地维护的 Message List 为主，SSE 负责增量更新，API 负责初始加载和兜底同步。
*   **ID 统一**：确保前端能第一时间获取后端生成的 Message ID，后续所有更新基于 ID 进行。
*   **零轮询（或最小化）**：正常对话期间完全依赖 SSE，仅在连接断开重连时进行一次全量/增量同步。
*   **清晰的状态机**：
    *   User Message: `sending` -> `sent` (Server Ack) -> `processed` (AI replying)。
    *   AI Message: `streaming` (typing) -> `completed`。

## 3. 关键决策点 (待确认)

### Q1: 后端接口调整
为了实现 ID 统一，我建议修改后端 `POST /api/chat` 接口。
*   **现状**：返回 `{"status": "queued", "message": "..."}`。
*   **建议**：返回 `{"status": "queued", "user_message_id": 123, "session_id": "..."}`。
*   **原因**：前端拿到 `user_message_id` 后，可以立即将本地临时 ID 替换为真实 ID。

### Q2: SSE 数据结构规范化
建议规范化 SSE 推送的消息格式，包含事件类型。
*   **格式**：
    ```json
    {
      "type": "ai_response", // 或 "status_update", "error"
      "id": 124,             // AI 消息 ID (如果生成了)
      "reply_to": 123,       // 回复哪条用户消息
      "content": "...",
      "action": "...",
      "is_final": false
    }
    ```

## 4. 下一步计划
1.  **Design**: 设计 `useChat` Hook 和新的组件结构。
2.  **Backend Change**: 调整后端接口以支持 ID 返回。
3.  **Implementation**: 实施前端重构。
