# DESIGN_Async_Message_Queue

## 1. 核心概念：Task (任务)
根据用户建议，引入显式的 **Task** 概念。
- **定义**: 一次 AI 唤醒处理过程，包含“读取一批 Pending 消息 -> 合并上下文 -> 调用 Workflow -> 生成回复 -> 落库”的完整生命周期。
- **原子性**: Task 是最小执行单元。Task 完成前，Trace 数据、AI 回复暂存内存或临时存储；Task 成功完成后，统一提交事务 (Commit)，确保 Trace、AI Message、User Message Status 更新的一致性。

## 2. 启动/触发机制 (Trigger)
为了确保 Task 能“及时启动”，需要多重触发保障：

### 2.1 实时触发 (Event Driven)
- **时机**: 用户调用 `POST /chat` 接口，消息落库 (`pending`) 成功后。
- **动作**: 立即尝试启动 Task (通过 `BackgroundTasks` 或 Redis Signal)。

### 2.2 启动自愈 (Startup Recovery)
- **时机**: Server 启动 (`lifespan` startup)。
- **动作**: 扫描 DB 中所有 `status='pending'` 的消息。按 `user_id` 分组，为每个有积压消息的用户触发一次 Task。
- **目的**: 处理服务宕机重启期间遗留的消息。

### 2.3 周期巡检 (Watchdog / Cron)
- **时机**: 每隔 N 秒 (如 60s)。
- **动作**: 扫描 DB 中 `status='pending'` 且 `created_at < (now - timeout)` 的消息。
- **目的**: 兜底。防止 Redis 信号丢失、Background Task 异常退出等导致的“僵尸消息”。

## 3. 详细流程设计

### 3.1 Task 执行流程
1.  **Lock**: 尝试获取 `lock:user:{id}`。若失败，说明该用户已有 Task 在跑，当前触发忽略（正在跑的 Task 跑完前会再次检查）。
2.  **Loop**: 进入处理循环。
    a. **Fetch**: 从 DB 查询该用户所有 `status='pending'` 的消息 (按时间正序)。
    b. **Check**: 如果没有消息 -> `Break Loop`。
    c. **Mark Processing**: (可选) 将这批消息状态改为 `processing`，防止被 Watchdog 重复捞取。
    d. **Merge**: 将多条消息合并为 Input Text。
    e. **Execute Workflow**: 执行 AI 生成逻辑。
    f. **Commit Transaction**:
        - 保存 AI 回复 (ChatHistory)。
        - 保存 Trace 数据 (WorkflowTrace)。
        - 更新那批 User 消息状态 `pending/processing` -> `completed`。
    g. **Notify**: 推送 SSE 事件。
3.  **Unlock**: 释放锁。

### 3.2 异常处理
- 如果 Task 执行失败（如 LLM 超时）：
    - 事务回滚。
    - 消息状态回退为 `pending` (或增加 `retry_count`)。
    - 释放锁。
    - 等待下一次 Watchdog 捞取重试。

## 4. 数据库变更
- **ChatHistoryDB**:
    - `status`: `pending` | `processing` | `completed` | `failed`
    - `group_id` (可选): 用于标记哪几条 User 消息被归为一个 Task 处理了 (即对应哪条 AI 回复)。
    - `retry_count`: 失败重试次数。

## 5. 模块划分
- `app/core/scheduler.py`: 负责 Watchdog 调度。
- `app/services/chat_task.py`: 封装 Task 的核心逻辑 (Lock, Fetch, Execute, Commit)。
- `app/api/endpoints/chat.py`: 负责接收请求、落库、触发 Task。

## 6. 确认
此设计满足：
1. **原子性 Task**: 确保数据完整性。
2. **全场景覆盖**: 启动时、运行时、异常时都能处理 Pending 消息。
