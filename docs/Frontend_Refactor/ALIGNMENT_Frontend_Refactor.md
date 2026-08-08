# ALIGNMENT: 前端工作流编排模块重构

## 1. 项目上下文分析

### 1.1 现有架构
- **后端**: FastAPI + LangGraph。最新的工作流逻辑引入了并行执行节点 (`analyze_communication_style`, `retrieve`, `summarize_topic`, `ensure_portrait` 并行运行) 和状态共享机制 (State-based)。
- **前端**: React + Ant Design + ReactFlow。使用 `WorkflowVisualizer.tsx` 组件从后端 `/api/workflow` 获取图结构并渲染。
- **可视化**: 目前使用 `dagre` 算法进行自动布局。节点组件为 `TraceNode.tsx`。

### 1.2 业务需求
- **重构前端工作流编排**: 适配后端最新的并行处理逻辑。
- **识别 LLM 调用**: 明确标识哪些节点调用了大模型。
- **优化展示**: 提升并行节点的可视化效果，清晰展示数据流向和状态变化。

### 1.3 现有约束
- 保持现有的 ReactFlow 技术栈。
- 复用现有的 `TraceNode` 组件结构，但在其基础上扩展。
- 不破坏现有的 API 契约 (后端 `/api/workflow` 返回 `nodes` 和 `edges`)。

## 2. 需求理解确认

### 2.1 核心需求
1.  **并行流可视化**: 确保前端能清晰展示后端新引入的并行分支结构。
2.  **LLM 节点标识**: 在图谱中高亮或打标调用 LLM 的节点 (`analyze_communication_style`, `summarize_topic`, `ensure_portrait`, `agent_thoughts`, `generate_response`)。
3.  **状态可视化更新**: 确保节点详情（Input/Output）能正确展示新的 State 数据结构（如 `internal_tasks` 并行任务结果）。

### 2.2 边界确认
- **范围**: 仅涉及 `WorkflowVisualizer.tsx`, `TraceNode.tsx` 及相关样式调整。后端 `/api/workflow` 如果需要额外元数据（如 `is_llm_node`），可能需要微调后端。
- **不涉及**: 改变后端核心业务逻辑或数据库结构。

## 3. 疑问与澄清

### 3.1 自动识别 vs 手动标记
- **问题**: 前端如何知道哪些节点是 LLM 节点？
- **策略**: 
    1.  **后端标记 (推荐)**: 修改 `/api/workflow`，在返回节点数据时增加 `is_llm` 字段。
    2.  **前端硬编码**: 前端维护一份 LLM 节点 ID 列表。
    - **决策**: 采用 **后端标记** 方案，更具扩展性。需修改 `server.py` 中的 `get_workflow_graph`。

### 3.2 并行节点的展示
- **问题**: Dagre 布局是否足够清晰展示并行？
- **策略**: Dagre 通常能处理，但可能需要调整间距 (`ranksep`, `nodesep`) 确保并行分支不重叠挤压。

## 4. 智能决策

- **决策 1**: 修改后端 `get_workflow_graph` 接口，为节点添加 `metadata`，包含 `is_llm`, `is_parallel` 等标记。
- **决策 2**: 更新前端 `TraceNode`，根据 `metadata` 渲染 "LLM" 徽章或特殊边框。
- **决策 3**: 调整 `WorkflowVisualizer` 的布局参数，优化并行展示。

## 5. 最终共识 (Consensus Draft)

- **目标**: 实现一个能真实反映后端并行逻辑、清晰标识 LLM 调用、用户体验友好的工作流可视化模块。
- **交付物**: 
    - 更新后的 `server.py` (API 增强)
    - 更新后的 `WorkflowVisualizer.tsx` (布局优化)
    - 更新后的 `TraceNode.tsx` (UI 增强)
