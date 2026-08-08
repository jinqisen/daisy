# 架构设计 (Design) - 消除重复 DB 查询

## 1. 数据流设计

```mermaid
graph TD
    A[Start: analyze_emotion] -->|Preload DB Data| B(State Update)
    B -->|State: {common_settings, active_profiles}| C[Node: summarize_topic]
    B -->|State| D[Node: ensure_portrait]
    B -->|State| E[Node: analyze_style]
    B -->|State| F[Node: agent_thoughts]
    B -->|State| G[Node: generate_response]
    
    C -.->|Read| S[State Cache]
    D -.->|Read| S
    E -.->|Read| S
    F -.->|Read| S
    G -.->|Read| S
```

## 2. 核心组件变更

### 2.1 AgentState (state.py)
新增字段：
- `common_settings`: 存储通用配置对象。
- `active_profiles`: 存储活跃角色配置列表。

### 2.2 Entry Node (emotion.py)
逻辑变更：
- 在执行情感分析前，检查 State 中是否已有数据。
- 若无，调用 `tools.py` 中的函数从 DB 加载数据并更新 State。
- 使用 `asyncio` 处理异步 DB 调用。

### 2.3 Consumption Nodes (generation.py)
涉及节点：`summarize_topic`, `ensure_portrait`, `analyze_style`, `agent_thoughts`, `generate_response`
逻辑变更：
- 读取：`state.get("common_settings")`
- 判断：若存在则直接使用（记录 Cache Hit 日志）。
- 回退：若不存在（None），则调用 DB 函数获取并回填 State（记录 Cache Miss 日志）。

## 3. 异常处理
- DB 查询失败时，捕获异常并记录 Error 日志，确保工作流不崩溃（可降级为默认值或空列表）。
- 确保 Python `asyncio` 事件循环在同步/异步混合环境下的正确获取。
