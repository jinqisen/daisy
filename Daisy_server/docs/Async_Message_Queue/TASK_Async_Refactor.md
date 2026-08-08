# TASK_Async_Refactor

## 1. 任务概述
引入 `arq` 框架实现异步消息队列，并重构项目目录结构以适应未来的多智能体（Multi-Agent）扩展。

## 2. 目录结构重构 (Refactoring)
为了支持多智能体 Task，建议将 Worker 相关逻辑独立出来。

**变更前**:
```
app/
  crew/        (包含业务逻辑)
  services/    (包含 LLM, Memory 等服务)
  api/         (HTTP 接口)
```

**变更后**:
```
app/
  tasks/               # [NEW] 存放所有异步任务定义
    __init__.py
    chat_task.py       # 聊天主任务
    agent_tasks/       # [Future] 未来多智能体子任务
      researcher.py
    worker.py          # ARQ Worker 配置与启动入口
  core/
    ...
  services/
    ...
```

## 3. 子任务分解

### Task 1: 引入依赖与配置
- [ ] 修改 `requirements.txt` 添加 `arq`。
- [ ] 修改 `app/core/config.py` 添加 Redis 配置 (ARQ 需要)。
- [ ] 修改 `app/core/redis.py` 提供 ARQ 所需的 Redis Settings。

### Task 2: 数据库模型变更
- [ ] 修改 `app/models/chat.py` (`ChatHistoryDB`)：
    - 添加 `status` 字段 (pending, processing, completed, failed)。
    - 添加 `task_id` 字段 (关联 ARQ Job ID，可选)。

### Task 3: 实现 Task 逻辑 (`app/tasks/`)
- [ ] 创建 `app/tasks/chat_task.py`:
    - 实现 `chat_task(ctx, user_id)` 函数。
    - 逻辑：Lock -> Loop (Fetch DB -> Workflow -> Save DB -> SSE Push)。
- [ ] 创建 `app/tasks/worker.py`:
    - 定义 `WorkerSettings` (functions, on_startup, on_shutdown)。

### Task 4: API 改造 (Producer)
- [ ] 修改 `app/api/server.py` (`POST /chat`):
    - 不再执行 Workflow。
    - 仅执行：Insert DB (Pending) -> `arq_pool.enqueue_job('chat_task', user_id)`.
    - 返回 200 OK。
- [ ] 新增 `GET /chat/stream` (SSE):
    - 使用 Redis PubSub 或轮询 DB 状态推送回复给前端。

### Task 5: 启动脚本与部署
- [ ] 修改 `app/main.py`: 在 startup 事件中初始化 ARQ 连接池。
- [ ] 创建新的启动脚本 `run_worker.ps1` / `run_worker.sh` 用于启动 ARQ Worker。
- [ ] (可选) 修改 `supervisord` 或 `docker-compose` 同时启动 API 和 Worker。
    - *初期简化*: 为了方便，可以在 `app/main.py` 的 `lifespan` 中启动一个嵌入式的 Worker (仅限开发环境)，或者在 Docker 中运行双进程。

## 4. 依赖关系图
Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 5

## 5. 验收标准
1.  用户发消息，API 立即返回。
2.  后台 Worker 自动捞取消息并处理。
3.  处理完成后，数据库状态更新为 `completed`。
4.  (SSE 部分视前端配合情况，先保证后端逻辑通畅)。
