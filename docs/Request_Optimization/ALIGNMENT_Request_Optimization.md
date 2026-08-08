# 任务对齐文档：前端请求优化

## 1. 原始需求
用户反馈前端一直不停地给后端发送请求，需要排查原因并优化。

## 2. 问题分析
经过代码审查，发现问题的根源在于 **React Hooks 依赖项不稳定** 导致的无限循环：

1.  **Callback 引用不稳定**：
    - `App.tsx` 中的 `handleStateUpdate` 和 `handleHistoryLoad` 没有使用 `useCallback` 包裹。
    - 每次 `App` 组件渲染（例如状态更新时），这两个函数都会生成新的引用。

2.  **Effect 依赖触发重连**：
    - `useChat.ts` 中的 `useEffect` 依赖了 `onStateUpdate`。
    - 当 `App` 传入新的 `onStateUpdate` 时，`useEffect` 重新执行。
    - `useEffect` 执行会断开并重建 SSE 连接。

3.  **循环触发**：
    - SSE 连接建立 -> `onopen` -> 调用 `loadHistory` -> 更新父组件状态 -> `App` 重渲染 -> 生成新 `handleStateUpdate` -> `useChat` 收到新 props -> `useEffect` 重运行 -> SSE 重连 -> 循环往复。

## 3. 解决方案
### 1. 稳定化 Props (App.tsx)
- 使用 `useCallback` 包裹 `handleStateUpdate` 和 `handleHistoryLoad`，确保在组件重渲染时保持引用稳定。

### 2. 增强 Hook 健壮性 (useChat.ts)
- 使用 `useRef` 保存 `onStateUpdate` 和 `onHistoryLoad` 的最新引用。
- 从 `useEffect` 依赖数组中移除 `onStateUpdate`，改为在回调内部通过 `ref.current` 调用。
- 这样即使父组件传递了不稳定的 callback，也不会导致 SSE 连接断开重连。

## 4. 验收标准
- [x] 前端不再出现无限重复的 SSE 连接请求。
- [x] 聊天功能和状态更新功能保持正常。
- [x] 代码通过编译。
