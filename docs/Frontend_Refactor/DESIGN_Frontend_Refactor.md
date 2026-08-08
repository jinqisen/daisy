# DESIGN: 前端工作流编排模块重构

## 1. 整体架构

### 1.1 数据流向
```mermaid
graph LR
    Backend[Backend (LangGraph)] -->|Structure & Metadata| API[/api/workflow]
    API -->|JSON| Visualizer[WorkflowVisualizer]
    Visualizer -->|Layout (Dagre)| ReactFlow
    ReactFlow -->|Render| TraceNode
```

### 1.2 核心组件设计

#### A. Backend (`server.py`)
- **Metadata Registry**:
  ```python
  NODE_METADATA = {
      "analyze_communication_style": {"label": "Comm. Style", "is_llm": True, "icon": "psychology"},
      "summarize_topic": {"label": "Summarize Topic", "is_llm": True, "icon": "summarize"},
      "ensure_portrait": {"label": "Ensure Portrait", "is_llm": True, "icon": "face"},
      "agent_thoughts": {"label": "Agent Thoughts", "is_llm": True, "icon": "brain"},
      "generate": {"label": "Generate Response", "is_llm": True, "icon": "edit"},
      "retrieve": {"label": "Retrieve Memory", "is_llm": False, "icon": "database"},
      # ... others
  }
  ```

#### B. Frontend (`TraceNode.tsx`)
- **Props Interface**:
  ```typescript
  interface TraceNodeData {
      label: string;
      is_llm?: boolean;
      trace?: any;
      // ...
  }
  ```
- **Visual Style**:
  - LLM Nodes: Purple/Blue border or glow effect. "LLM" badge in header.
  - Parallel Nodes: Standard styling but positioned horizontally by parent layout.

#### C. Frontend (`WorkflowVisualizer.tsx`)
- **Layout Config**:
  - Increase `nodesep` (node separation) to accommodate parallel nodes side-by-side.
  - Increase `ranksep` (rank separation) for clearer vertical flow.

## 2. 接口契约 (API Schema Update)

**GET /api/workflow**
Response:
```json
{
  "nodes": [
    {
      "id": "analyze_communication_style",
      "data": {
        "label": "Comm. Style",
        "is_llm": true,   // New Field
        "icon": "psychology" // Optional
      },
      "type": "traceNode"
    },
    ...
  ],
  "edges": [...]
}
```

## 3. 异常处理
- 如果后端未返回 `is_llm`，默认为 false。
- 如果布局计算失败，回退到默认垂直排列。
