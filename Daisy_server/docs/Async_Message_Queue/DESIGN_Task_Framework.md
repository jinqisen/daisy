# DESIGN_Task_Framework

## 1. 需求升级：多智能体与可扩展性
用户强调了 Task 机制的“成熟合理性”和“未来可扩展性”。
目前的场景是：
- **当前**: 每个用户一个 AI 助理（单 Task）。
- **未来**: 多智能体（Multi-Agent）场景，每个智能体可能都是一个独立的 Task，需要独立调度、执行、状态管理。

这不仅是简单的“异步队列”，而是一个 **分布式任务调度系统** 的雏形。我们需要引入一个成熟的框架，而不是手搓简单的 Redis Loop。

## 2. 框架选型分析

### 选项 A: Celery (Python 事实标准)
- **优点**: 极其成熟，生态丰富，支持 Redis/RabbitMQ，有完善的重试、定时任务、工作流（Chain/Group/Chord）机制。
- **缺点**: 相对较重，Worker 是独立进程，部署稍微复杂（需要额外部署 Celery Worker）。
- **适用性**: 非常适合需要高可靠、复杂编排的任务系统。

### 选项 B: APScheduler (轻量级调度)
- **优点**: 进程内运行，轻量，支持 Cron/Interval/Date 触发。
- **缺点**: 主要用于定时任务，对于“事件驱动的即时任务队列”支持不如 Celery 强大（虽然也可以做）。
- **适用性**: 适合定时巡检，不适合作为高吞吐的消息队列消费者。

### 选项 C: ARQ (Asyncio Redis Queue)
- **优点**: 专为 `asyncio` 设计，轻量，高性能，原生支持异步。比 Celery 轻很多，比手搓强很多。
- **缺点**: 功能不如 Celery 全面（如复杂的 Canvas 编排），生态稍弱。
- **适用性**: 非常适合 FastAPI 这种全异步架构。

### 选项 D: Temporal (工作流引擎 - 终极方案)
- **优点**: 专为“持久化执行”设计，天生支持“长运行、可重试、状态保持”的任务。非常适合 AI Agent 这种长流程。
- **缺点**: 引入了全新的技术栈（Temporal Server），运维成本高，对当前项目可能过重。

## 3. 推荐方案：ARQ (Asyncio Redis Queue)
考虑到 Daisy 目前是基于 FastAPI 的全异步架构，且希望保持相对轻量但具备扩展性，**ARQ** 是最佳平衡点。

### 为什么选择 ARQ？
1.  **原生 Async**: 完美契合 FastAPI 的 `async def`，不需要像 Celery 那样处理同步/异步的桥接痛苦。
2.  **Redis 驱动**: 直接利用现有的 Redis 设施，不需要引入 RabbitMQ。
3.  **Job 机制**: 支持 `enqueue_job`, `retry`, `job_result` 等标准队列功能。
4.  **轻量级 Worker**: 可以很容易地在单独的容器或进程中启动 Worker。
5.  **未来扩展**:
    - **多智能体**: 每个智能体可以是一个不同的 Function，或者通过参数区分。
    - **任务编排**: 虽然不如 Celery 强，但通过代码逻辑可以实现基本的串行/并行。

## 4. 架构设计 (基于 ARQ)

### 4.1 核心组件
- **Producer (FastAPI)**:
    - 接收用户请求 -> 落库 (Pending) -> `await redis.enqueue_job('chat_task', user_id)`。
- **Broker (Redis)**:
    - 存储任务队列。
- **Worker (ARQ Worker)**:
    - 独立运行的进程（或在开发环境中与 API 同进程启动）。
    - 注册 `chat_task` 函数。
    - 包含 `on_startup` (数据库连接) 和 `on_shutdown`。

### 4.2 Task 实现 (`chat_task`)
```python
async def chat_task(ctx, user_id: int):
    # 1. 获取分布式锁 (防止同一个用户的 Task 并发)
    async with redis_lock(f"lock:user:{user_id}"):
        # 2. 循环处理 (Loop)
        while True:
            # 3. 查库 (Source of Truth)
            pending_msgs = await db.get_pending_messages(user_id)
            if not pending_msgs:
                break
            
            # 4. 执行 AI 逻辑
            response = await workflow.run(pending_msgs)
            
            # 5. 事务提交 (Commit)
            await db.save_response_and_update_status(response, pending_msgs)
            
            # 6. 推送 (SSE)
            await sse.publish(user_id, response)
```

### 4.3 多智能体扩展
未来如果有多个智能体（如 "Researcher", "Writer"），可以定义不同的 Job：
- `enqueue_job('research_task', query=...)`
- `enqueue_job('write_task', outline=...)`
ARQ Worker 可以同时消费多种类型的 Job。

## 5. 实施步骤
1.  引入 `arq` 依赖。
2.  创建 `app/worker.py` 定义 Worker Settings 和 Functions。
3.  在 FastAPI 中集成 ARQ 客户端。
4.  修改 `/chat` 接口为入队模式。
5.  修改 Docker 启动脚本，启动 ARQ Worker。

是否同意引入 **ARQ** 作为任务框架？
