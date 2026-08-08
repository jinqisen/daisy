# Daisy Server 向 Claude Skills (MCP) 迁移技术方案

## 1. 背景与目标

当前 `Daisy_server` 的工具调用（Tool Use）机制基于传统的 ReAct 模式，通过手动构造 Prompt 和解析 JSON 来实现。这种方式存在以下问题：
- **脆弱性**：依赖 LLM 输出严格的 JSON 格式，容易解析失败。
- **高耦合**：工具定义与业务逻辑紧密耦合。
- **扩展困难**：新增工具需要修改核心代码。

本方案旨在引入 **Model Context Protocol (MCP)**，将工具调用迁移到标准化的 Client-Server 架构，利用 LLM (如 GPT-4, Claude 3.5) 的原生 Tool Calling 能力，提升系统的健壮性和可扩展性。

## 2. 架构设计

### 2.1 总体架构

我们将采用 **MCP Stdio 模式**。`Daisy_server` 作为 MCP Client，通过标准输入/输出与作为 MCP Server 的子进程通信。

```mermaid
graph TD
    subgraph "Daisy Server (MCP Client)"
        Workflow[Workflow Node (react.py)] -->|Request Tools| MCPService
        MCPService[MCP Service] -->|Stdio/JSON-RPC| MCPServerProcess
        MCPService -->|Convert to LangChain Tools| Workflow
    end

    subgraph "Daisy Skills (MCP Server)"
        MCPServerProcess[Python Process]
        Tools[Tool Implementations]
        
        MCPServerProcess -- Executes --> Tools
    end
```

### 2.2 核心组件变更

#### A. 新增组件：MCP Server (`Daisy_skills/`)
- 独立于主服务运行的 Python 脚本。
- 使用 `mcp` SDK 定义工具 (Search, Calculator, etc.)。
- 负责具体的工具逻辑执行。

#### B. 新增组件：MCP Client Service (`app/services/mcp_service.py`)
- 负责启动和管理 MCP Server 子进程。
- 维护 `ClientSession`。
- 提供 `get_tools()` 方法，将 MCP 工具定义转换为 LangChain `BaseTool` 或 OpenAI Tool Schema。

#### C. 重构组件：ReAct Node (`app/workflow/nodes/react.py`)
- **移除**：手动 Prompt 拼接 (`You decide whether to call...`)。
- **移除**：手动 JSON 解析 (`json.loads(...)`)。
- **新增**：使用 `llm.bind_tools()` (LangChain 标准接口)。
- **逻辑**：
    1. 获取可用工具列表。
    2. 调用 LLM (带 Tools 绑定)。
    3. 检查 `tool_calls`。
    4. 执行工具并回传结果。

## 3. 实施步骤

### Phase 1: 基础设施准备 (Infrastructure)
1.  **依赖更新**: 在 `Daisy_server` 中引入 `mcp` 库。
2.  **Server 固化**: 将 POC 阶段的 `Daisy_skills/server.py` 完善为生产级代码 (日志对接、配置加载)。

### Phase 2: Client 集成 (Integration)
1.  **Service 实现**: 创建 `MCPService` 单例，实现进程生命周期管理。
2.  **工具适配**: 实现 `MCPToolAdapter`，将 MCP 的 `CallToolRequest` 封装为 LangChain 可调用的对象。

### Phase 3: 工作流重构 (Refactoring)
1.  **修改 React 节点**: 改造 `tool_check` 函数，从 `MCPService` 获取工具，使用 Native Tool Calling。
2.  **兼容性处理**: 保留 Config 开关，允许回退到旧版逻辑 (Feature Flag)。

### Phase 4: 迁移与清理 (Migration)
1.  **迁移 SearchTool**: 将华为云搜索逻辑移入 MCP Server。
2.  **迁移 CalculatorTool**: 将计算器逻辑移入 MCP Server。
3.  **清理**: 删除 `app/core/tools.py` 中的旧代码。

## 4. 风险与对策

| 风险点 | 影响 | 对策 |
| :--- | :--- | :--- |
| **进程管理** | 子进程僵死或意外退出 | 在 `MCPService` 中实现健康检查和自动重启机制。 |
| **延迟增加** | 跨进程通信带来微小延迟 | MCP 基于 Stdio 极为高效，且工具执行本身耗时远大于通信耗时，影响可忽略。 |
| **模型兼容性** | 某些轻量模型不支持 Native Tool Calling | `MCPService` 可提供降级模式，将工具描述转为 Prompt (类似当前逻辑)，但保持接口统一。 |

## 5. 下一步行动
建议立即开始 Phase 1，优先打通链路。
