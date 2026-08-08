# 任务：重构对话组件 (ChatInterface) 设计文档

## 1. 系统架构设计

### 1.1 模块划分
我们将 `ChatInterface.tsx` 拆分为以下部分：
1.  **`useChat` Hook**: 核心逻辑层。负责状态管理、API 调用、SSE 连接、消息队列处理。
2.  **`ChatLayout` Component**: UI 骨架。负责布局、Header、Drawer 等。
3.  **`MessageList` Component**: 消息渲染列表。
4.  **`MessageInput` Component**: 输入框区域。

### 1.2 数据流向图
```mermaid
graph TD
    User[用户输入] -->|Send| useChat
    useChat -->|POST /chat| API
    API -->|Ack (msg_id)| useChat
    useChat -->|Update Temp ID| State[Message State]
    
    SSE[SSE Stream] -->|Event| useChat
    useChat -->|Append/Update| State
    
    State -->|Props| MessageList
    State -->|Props| MessageInput
```

## 2. 接口契约变更

### 2.1 `POST /api/chat` (Backend Update)
*   **Request**: Unchanged.
*   **Response**:
    ```json
    {
        "status": "queued",
        "data": {
            "user_message_id": 101, // New Field
            "session_id": "abc-123",
            "timestamp": "2023-..."
        }
    }
    ```

### 2.2 SSE Event Structure (Frontend Interpretation)
前端将解析以下类型的 SSE 数据：
1.  **Standard Response**: `{ "response": "..." }` (兼容现有逻辑)
2.  **Enhanced Response** (Recommended):
    ```json
    {
        "type": "content",
        "id": 102, // AI Message ID (Optional/Future)
        "content": "Hello world",
        "action": "<action>smile</action>"
    }
    ```
    *注：本次重构暂保持对现有 SSE 格式的兼容，但在 Hook 中预留结构化解析能力。*

## 3. `useChat` Hook 详细设计

### 3.1 State Definition
```typescript
interface Message {
  id: string | number; // Local temp ID (string) or Backend ID (number)
  role: 'user' | 'ai';
  content: string;
  action?: string;
  status: 'sending' | 'sent' | 'error'; // 仅用于 UI 展示
  createdAt: number;
}

const [messages, setMessages] = useState<Message[]>([]);
const [isConnected, setIsConnected] = useState(false); // SSE Status
```

### 3.2 核心方法
1.  **`sendMessage(content: string)`**:
    *   生成 `tempId` (e.g., `temp-${Date.now()}`).
    *   `setMessages` 添加 optimistic UI message.
    *   调用 `api.post('/chat')`.
    *   成功：更新 `messages`，将 `tempId` 替换为 `res.user_message_id`，状态置为 `sent`。
    *   失败：状态置为 `error`。

2.  **`handleSSEMessage(event)`**:
    *   解析 content/action。
    *   **关键逻辑**：由于当前 SSE 不带 ID，我们假设接收到的流式数据属于“当前正在进行的 AI 回复”。
    *   查找最后一条消息：
        *   如果是 `role: 'ai'` 且状态未完结（暂定 SSE 没结束标记，所以总是 append 到最后一条 AI 消息？或者每条 SSE 都是独立的增量？不，现有后端是一次性推一段）。
        *   **修正**：现有 SSE 是 `yield f"data: {message['data']}\n\n"`，其中 `data` 是 JSON。如果是一次性推送完整段落，则直接 `append` 新的 AI 消息。

### 3.3 废弃 Polling
*   移除 `setInterval` 轮询。
*   在 `useEffect` 初始化时调用一次 `loadHistory()`。
*   在 SSE `onerror` 并重新连接成功后，调用一次 `loadHistory()` 确保数据同步。

## 4. 迁移计划

1.  **Phase 1: Backend Update**
    *   修改 `Daisy_server/app/api/server.py`，确保 `/chat` 返回 ID。

2.  **Phase 2: Frontend Refactor**
    *   创建 `src/hooks/useChat.ts`。
    *   重写 `ChatInterface.tsx` 使用该 Hook。
    *   清理旧的轮询和合并逻辑。

3.  **Phase 3: Verification**
    *   测试消息发送状态流转。
    *   测试刷新页面后的历史记录加载。
    *   测试断网重连。

## 5. 质量保障
*   **TypeScript**: 全面类型定义。
*   **Error Handling**: 网络请求失败的优雅降级。
*   **UX**: 发送中禁用输入框（可选），加载状态提示。
