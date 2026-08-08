# ALIGNMENT_Async_Message_Queue

## 1. 原始需求
用户指出当前的同步等待回复模式（User 发消息 -> 等待 AI 生成 -> 收到回复）不符合真实微信对话体验。
期望改为**异步队列模式**：
1.  **即时存储**: 用户发消息后立即存入“待处理队列”，前端不转圈等待。
2.  **单线程/Agent**: 每个用户有一个专属的 AI 助理线程/Agent。
3.  **批量读取**: AI 线程每次被唤醒时，一次性读取队列中该用户**所有**未处理的消息，合并视为“一条”输入进行回复。
4.  **原子出队**: 消息一旦被 AI 线程读取，即视为“已接收/处理中”，从等待队列移除。
5.  **后台持久化**: 即使用户退出 APP，AI 线程仍需完成当前回复生成。
6.  **忙碌排队**: 如果 AI 正在生成回复（忙碌状态），用户新发的每一条消息都直接进入队列等待，直到 AI 完成上一轮并在下一轮循环中批量读取。

## 2. 现状分析
### 2.1 当前架构
- **同步 HTTP**: `POST /api/chat` 是一个阻塞接口，直到 Workflow 执行完毕才返回。
- **单条处理**: 每次请求处理一条消息。如果用户连续发 3 条，会有 3 个并发的 HTTP 请求（或者前端排队发），导致 AI 可能分别回复 3 次，甚至产生幻觉（因为 Context 还没更新）。
- **无队列**: 目前没有显式的消息队列（Redis List 或 Celery），依赖 HTTP 请求生命周期。

### 2.2 核心挑战
- **并发控制**: 如何确保对同一个用户，同一时间只有一个 AI 任务在跑？(需要分布式锁或 Actor 模型)
- **消息合并**: 需要改变 Input 结构，支持 `List[Message]` 而非 `str`。
- **前端交互变更**: 前端不能再 `await fetch` 等结果，而是发完即走，通过 `SSE` (Server-Sent Events) 或 `WebSocket` 或 `Polling` 被动接收 AI 的回复。

## 3. 拟定技术方案 (Draft)
### 3.1 消息队列 (Redis)
- 使用 Redis List: `chat:queue:{user_id}`
- 用户发消息 -> `LPUSH chat:queue:{user_id} message_json` -> 立即返回 HTTP 200 OK。

### 3.2 任务调度 (Producer-Consumer)
- **触发机制**:
    - 方案 A (后台轮询): 有一个 Worker 进程不断轮询活跃用户的队列。
    - 方案 B (事件触发): `POST /api/chat` 写入 Redis 后，尝试触发/唤醒该用户的 Agent。如果 Agent 忙（Redis Lock），则跳过（Agent 完事后会自己检查队列）。

### 3.3 锁与状态 (Redis Lock)
- `chat:lock:{user_id}`: 标记 AI 正在处理中。
- **处理流程**:
    1. 尝试获取锁 `SET chat:lock:{user_id} 1 NX EX 300`。
    2. 如果获取失败 -> 结束（说明有线程在跑，它跑完会检查队列）。
    3. 如果获取成功 -> 
        a. `LRANGE` 获取所有消息。
        b. `DEL` 清空队列 (原子性注意：最好用 Lua 或 RPOP)。
        c. 调用 LangGraph Workflow (传入合并后的文本)。
        d. 生成结果存入 DB。
        e. 推送给前端 (SSE/WS)。
        f. **关键**: 释放锁之前，再次检查队列是否有新消息？如果有，循环执行 a；如果没有，释放锁并退出。

### 3.4 消息合并策略
- 将多条消息合并为:
  ```
  User: [10:01] 你好
  User: [10:01] 在吗
  User: [10:02] 我有个问题
  ```
  作为单轮对话的 Input。

## 4. 待确认问题
1.  **前端通信**: 用户更倾向于 SSE (单向流) 还是 WebSocket (双向)？鉴于目前是 HTTP POST，改 SSE 可能改动最小且符合“接收通知”的语义。
2.  **历史兼容**: 现有的 ChatHistoryDB 是一条一条存的。合并处理后的回复，对应哪条 User Message？通常是对应“这一批的最后一条”，或者在 DB 中插入一条合并后的 User Message？
    - *建议*: 保持原始消息颗粒度存 DB (User Message)，AI 回复 (AI Message) 指向这一批的最后一条 ID，或者逻辑上关联这一批。
    - *简化方案*: 为了 Memory 和 Context 简单，Workflow 看到的 Input 是合并文本，但在 Chat History 中，我们可能需要把这批消息都标记为“已响应”。

## 5. 决策
我们采用 **Redis Queue + 递归锁机制 + SSE 推送** 的方案。
这需要较大的架构重构：
1. 后端新增 Redis 队列逻辑。
2. 后端新增 SSE 接口 `/api/chat/stream` 或 `/api/events`。
3. 重构 `POST /api/chat` 为非阻塞。
4. 创建后台 Worker 或利用 FastAPI `BackgroundTasks` (但在分布式下不可靠，建议用 Redis 触发的独立逻辑)。

**考虑到项目规模，建议先在 FastAPI 内部用 `BackgroundTasks` + `Redis Lock` 实现轻量级异步。**
即：
API 收到请求 -> 存 Redis -> 触发 `process_user_queue(user_id)` (后台任务)。
`process_user_queue`:
  Lock? -> No: Return.
  Yes: Loop (Pop All -> Generate -> Notify) until Empty -> Unlock.

是否同意此方案？
