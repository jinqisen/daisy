# CONSENSUS: 前端工作流编排模块重构

## 1. 需求描述
用户要求基于后端最新的业务逻辑（并行执行、状态共享）重构前端工作流编排模块，并明确识别 LLM 调用位置。

## 2. 技术方案

### 2.1 后端增强 (API)
- 修改 `server.py` 中的 `get_workflow_graph` 函数。
- 维护一个 `NODE_METADATA` 字典，映射节点 ID 到元数据（如 `type`, `is_llm`, `description`）。
- 在 `/api/workflow` 响应中包含这些元数据。

### 2.2 前端重构 (Visualizer)
- **WorkflowVisualizer.tsx**:
    - 解析后端返回的新元数据。
    - 调整 Dagre 布局参数 (`ranksep=150`, `nodesep=80`) 以适应并行分支的宽度。
    - 增加图例 (Legend) 说明不同节点样式的含义。
- **TraceNode.tsx**:
    - 接收 `is_llm` 属性。
    - 如果是 LLM 节点，在卡片头部增加 "LLM" 标签或图标 (e.g., ✨ 或 🤖)。
    - 优化 `internal_tasks` 的展示（如果之前未完全适配）。

### 2.3 验收标准
1.  **可视化准确性**: 能够看到 `analyze_communication_style`, `retrieve`, `summarize_topic`, `ensure_portrait` 呈现为并行结构（即从 `analyze` 分出多条线，最终汇聚）。
2.  **LLM 标识**: 以下节点必须有明显标识：
    - `analyze_communication_style`
    - `summarize_topic`
    - `ensure_portrait`
    - `agent_thoughts`
    - `generate_response`
3.  **无错误**: 前端控制台无布局或渲染错误，后端 API 正常响应。

## 3. 任务边界
- 仅限于工作流可视化相关组件。
- 不涉及实际的 LLM 调用逻辑修改。
