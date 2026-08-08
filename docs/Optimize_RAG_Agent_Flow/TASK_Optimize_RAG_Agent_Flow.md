# 任务分解：优化 RAG 与 Agent 的交互流程

## 依赖关系
Task 1 -> Task 2 -> Task 3

## 详细任务

### Task 1: 实现 `ThoughtFilter` 类
- **目标**: 创建一个流式过滤器，用于移除 `<thought>...</thought>` 块。
- **文件**: `src/core/chat_manager.py` 或 `src/api/chat.py` (建议放在 `chat.py` 作为一个 helper 类，或者放在 `utils`)。
- **输入**: 文本流 chunk。
- **输出**: 过滤后的文本流。
- **验收**: 单元测试验证各种边界情况（标签跨 chunk，无标签，只有标签）。

### Task 2: 更新 Prompt 构建逻辑
- **目标**: 修改 `_build_immersive_system_prompt` 以包含 CoT 指令。
- **文件**: `src/api/chat.py`。
- **内容**: 增加 `<thought>` 格式要求和 RAG 转化指令。

### Task 3: 集成过滤器到生成流程
- **目标**: 在 `event_generator` 和 `generate_ai_response` 中使用 `ThoughtFilter`。
- **文件**: `src/api/chat.py`。
- **步骤**:
    1. 实例化 `ThoughtFilter`。
    2. 在流式循环中调用 `filter.feed(chunk)`。
    3. 在循环结束调用 `filter.flush()`。
    4. 确保存储到数据库的消息 (`chat_manager.add_message`) 也是过滤后的内容（或者我们决定存储思考过程？建议存储过滤后的，保持历史记录整洁）。

### Task 4: 验证与微调
- **目标**: 运行对话，观察日志和前端输出。
- **验收**: 
    - 确保回复中不再包含 RAG 原文的机械复述。
    - 确保前端看不到 `<thought>` 标签。
    - 确保日志中（如果有打印）可以看到思考过程（可选，便于调试）。
