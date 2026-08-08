# 验收文档：重构对话组件

## 1. 任务概述
本次任务旨在重构 `ChatInterface` 组件，解决消息状态同步混乱、轮询效率低、ID 不统一等问题，并满足“消息落库即成功”、“SSE 实时推送”、“初始化全量加载”的需求。

## 2. 修改内容

### 2.1 后端 (`Daisy_server/app/api/server.py`)
*   **修改**: `POST /chat` 接口响应。
*   **内容**: 增加 `data` 字段，返回 `user_message_id`。
*   **目的**: 让前端能在发送后立即获得后端生成的唯一 ID，实现状态确权。

### 2.2 前端 Hook (`Daisy_front/src/hooks/useChat.ts`)
*   **新增**: 创建 `useChat` 自定义 Hook。
*   **功能**:
    *   **状态管理**: 统一管理 `messages`, `loading`, `isConnected`。
    *   **发送逻辑**: Optimistic UI -> API Call -> Update ID (Pending -> Sent)。
    *   **历史加载**: 组件挂载时调用 `/api/chat/history` 加载全量/最近记录。
    *   **SSE 监听**: 建立连接，接收 AI 推送，自动追加 AI 消息。

### 2.3 前端组件 (`Daisy_front/src/components/ChatInterface.tsx`)
*   **重构**: 移除所有内部状态逻辑，全权委托给 `useChat`。
*   **简化**: 代码行数大幅减少，专注于 UI 渲染。
*   **修复**: 解决了之前因轮询和 SSE 冲突导致的空消息、重复消息问题。

## 3. 验证情况

| 需求点 | 验证结果 | 备注 |
| :--- | :--- | :--- |
| **消息落库即成功** | ✅ 已实现 | 后端返回 ID，前端立即确认为 Sent |
| **SSE 实时推送** | ✅ 已实现 | AI 生成完成后推送，前端自动显示 |
| **初始化加载** | ✅ 已实现 | `useChat` 挂载时自动加载历史 |
| **代码规范** | ✅ 已符合 | 使用 TypeScript，注释完整 |

## 4. 后续建议
*   目前 SSE 推送的是完整文本。如果未来支持流式打字机效果（Token by Token），需调整 `useChat` 的 SSE 处理逻辑（支持 append 模式）。
*   可以进一步优化网络错误处理，增加自动重试机制。
