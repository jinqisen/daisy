# 任务一致性确认 (Alignment) - 消除重复 DB 查询

## 1. 原始需求
用户要求消除 LangGraph 工作流中重复的数据库查询，以提高性能并减少 I/O 开销。

## 2. 问题分析
- **现状**: `summarize_topic`, `ensure_portrait`, `analyze_style`, `agent_thoughts`, `generate_response` 等多个节点都重复查询了 `CommonSettings` 和 `ActiveProfiles`。
- **目标**: 将这些数据查询集中化，仅在工作流入口处查询一次，然后通过 State 传递给后续节点。

## 3. 技术方案
- **State 扩展**: 在 `AgentState` 中增加 `common_settings` 和 `active_profiles` 字段。
- **预加载**: 在入口节点 (`analyze_emotion` 或首个执行节点) 统一从 DB 获取数据并写入 State。
- **节点改造**: 修改后续所有节点，优先从 State 读取数据；若 State 中缺失（如直接调用子节点的场景），则回退到 DB 查询。

## 4. 验收标准
- 所有相关节点优先使用 State 数据。
- 数据库查询次数显著减少（通过日志验证）。
- 系统功能（聊天回复）保持正常。
