# CONSENSUS_Async_Message_Queue

## 1. 核心需求
实现**异步、队列化、原子化**的消息处理机制。
- 用户发消息 -> 入队 -> 立即返回。
- 单线程 Agent 批量捞取消息 -> 处理 -> 推送回复。

## 2. 数据可靠性挑战 (Redis 持久化)
用户提出了关键质疑：**如果 AI 还没处理，Redis 挂了，消息会不会丢？**
这是一个典型的数据一致性问题。

### 2.1 风险分析
如果仅仅将消息存入 Redis List (`LPUSH`)，虽然 Redis 有 RDB/AOF 持久化，但在极端断电或 Crash 情况下，AOF 可能有秒级数据丢失。且 Redis 数据通常被视为“临时”的。

### 2.2 解决方案：双写 (Dual Write) / 状态机模式
为了绝对可靠，我们不能只信赖 Redis。必须以 **数据库 (SQLite/PostgreSQL)** 为最终真理来源 (Source of Truth)。

**改进后的流程 (Write-Ahead Logging 思想):**

1.  **入库 (Persist)**: 用户发消息 -> **立即写入 SQLite `chat_history` 表**。
    - 关键点：标记状态 `status = 'pending'` (待处理)。
2.  **入队 (Notify)**: 写入 DB 成功后 -> `LPUSH` 消息 ID 到 Redis 队列。
    - *注意*: 这里 Redis 仅作为“通知通道”，仅存储 ID。
3.  **处理 (Process)**:
    - Agent 被唤醒。
    - 从 Redis 拿到 ID 列表（或者直接查 DB 中该用户所有 `status='pending'` 的消息）。
    - **推荐方式**: 直接查 DB。Redis 仅作为一个“有新消息了，快起来干活”的信号量（Signal）。这样即使 Redis 挂了、空了，Agent 只要被唤醒（比如定时巡检或用户新发消息再次唤醒），去 DB 一查就能把漏掉的消息补回来。
4.  **完成 (Commit)**:
    - AI 回复生成后。
    - 存入 AI 回复到 DB。
    - 将之前那批 User 消息的 `status` 更新为 `processed`。

### 2.3 容灾恢复
- **场景**: Redis 挂了重启，队列丢了。
- **后果**: Agent 暂时没收到信号。
- **恢复**: 用户发下一条消息时，或者系统重启时的自检脚本，会发现 DB 里有 `pending` 的消息，再次触发处理。或者增加一个低频的定时任务（每分钟）扫描 DB 中 `pending` 超过 1 分钟的消息并重新触发。

## 3. 最终架构方案

### 3.1 数据库变更
- `ChatHistoryDB` 表新增字段:
    - `status`: `enum('pending', 'processing', 'completed', 'failed')`，默认为 `completed` (兼容旧数据) 或 `pending` (新流程)。
    - 对于 User 消息，初始为 `pending`。
    - 对于 AI 消息，初始为 `completed`。

### 3.2 接口变更
- `POST /chat`:
    - 1. Insert DB (Status=Pending) -> Commit.
    - 2. Push Redis Signal.
    - 3. Trigger Background Task.
    - 4. Return 200 OK.

### 3.3 后台任务 (Consumer)
- Lock User.
- While True:
    - Query DB for `pending` messages (ORDER BY time ASC).
    - If None -> Break.
    - Update DB `pending` -> `processing`.
    - Merge Content.
    - Call AI.
    - Save AI Response.
    - Update DB `processing` -> `completed`.
    - Push SSE Event.
- Unlock.

### 3.4 前端变更
- 使用 SSE `/api/chat/stream` 监听回复。

## 4. 用户确认
此方案以 DB 为准，Redis 仅做加速和信令，**彻底解决了“Redis 挂掉导致丢消息”的问题**。是否同意？
