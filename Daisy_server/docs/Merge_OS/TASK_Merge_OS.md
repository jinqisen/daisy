# TASK_Merge_OS: 多人格内心OS融合优化实施任务

## 任务清单

### Task 1: 优化内心独白格式化逻辑
- **文件**: `app/workflow/nodes/generation.py`
- **目标**: 修改 `_format_task_outputs` 函数。
- **描述**: 
  - 将 `agent_thoughts` (Dict) 转换为带有权重的结构化文本。
  - 格式示例:
    ```text
    - [PersonaName] (Weight: 0.XX): ...
    ```
  - 标题改为 "Conflicting Inner Voices (Raw Data)".

### Task 2: 更新 CO-STAR Prompt 指令
- **文件**: `app/workflow/nodes/generation.py`
- **目标**: 修改 `_generate_costar_instruction` 函数。
- **描述**:
  - 在 `## T (Tone)` 或新开 `## I (Internal Process)` 章节。
  - 增加指令：要求模型首先输出 `[Final Inner Thought]: ...`，进行思维融合。
  - 增加指令：要求模型在融合后，另起一段输出最终回复。

### Task 3: 解析最终回复并剥离思维链
- **文件**: `app/workflow/nodes/generation.py`
- **目标**: 修改 `generate_response` 函数。
- **描述**:
  - 在获取 `response` 后，使用正则或字符串处理提取 `[Final Inner Thought]: ...` 内容。
  - 将提取出的思维内容记录到 `trace` 或日志中。
  - 确保返回给用户的 `response_parts` **不包含** 思维内容。

### Task 4: 验证
- **目标**: 运行一次对话，检查日志。
- **验收**:
  - 确认 Prompt 中包含 Raw Voices。
  - 确认 LLM 输出了 Final Inner Thought。
  - 确认最终回复不包含 OS 内容。
