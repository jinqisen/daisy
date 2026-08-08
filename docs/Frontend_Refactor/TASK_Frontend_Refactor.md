# TASK: 前端工作流编排模块重构

## 1. 任务拆分

### 1.1 Task 1: 后端 API 增强
- **目标**: 更新 `server.py` 中的 `/api/workflow` 接口。
- **内容**: 
  - 定义 `NODE_METADATA` 字典。
  - 在 `get_workflow_graph` 中注入元数据。
- **验证**: 访问 `/api/workflow`，检查响应 JSON 是否包含 `is_llm` 字段。

### 1.2 Task 2: 前端组件更新 (TraceNode)
- **目标**: 更新 `TraceNode.tsx` 以展示 LLM 标识。
- **内容**: 
  - 修改 `TraceNode` 组件接收 `is_llm` prop。
  - 添加 UI 元素（图标/标签）来标识 LLM 节点。
- **验证**: 运行前端，检查相关节点是否有特殊标识。

### 1.3 Task 3: 前端布局优化 (Visualizer)
- **目标**: 更新 `WorkflowVisualizer.tsx` 适配并行布局。
- **内容**: 
  - 调整 `dagre` 布局参数。
  - 确保 API 返回的新数据正确传递给 `TraceNode`。
- **验证**: 观察工作流图，确认并行分支清晰可见。

## 2. 依赖关系
Task 1 -> Task 3 -> Task 2 (可以并行，但建议按顺序集成)

## 3. 验收标准
- 所有 5 个 LLM 节点都有清晰标识。
- 工作流图正确展示并行结构。
- 现有功能（点击查看详情、历史回溯）不受影响。
