# 设计：优化 RAG 与 Agent 的交互流程

## 1. 模块设计

### 1.1 `ThoughtFilter` (流式过滤器)
负责在流式传输过程中实时剥离 `<thought>...</thought>` 标签及其内容。

**逻辑**:
- 维护 buffer。
- 状态机：`NORMAL`, `MAYBE_STARTING`, `IN_THOUGHT`, `MAYBE_ENDING`。
- 简单实现：由于 `<thought>` 比较长，可以只检测 `<` 开始缓冲，直到确认不是 tag。
- 或者更简单：因为标签固定，我们可以缓冲直到遇到 `>`，检查是否是 `<thought>`。
- **注意**: 由于 GPT 输出的不确定性，标签可能被分在不同的 chunk 中。

**Python 实现草稿**:
```python
class ThoughtFilter:
    def __init__(self):
        self.buffer = ""
        self.in_thought = False
        
    def feed(self, chunk: str) -> str:
        self.buffer += chunk
        output = ""
        
        while True:
            if not self.in_thought:
                # 寻找 <thought>
                start_idx = self.buffer.find("<thought>")
                if start_idx != -1:
                    # 找到了，输出之前的部分
                    output += self.buffer[:start_idx]
                    self.buffer = self.buffer[start_idx + 9:] # Skip <thought>
                    self.in_thought = True
                else:
                    # 没找到完整标签，检查是否有部分标签在末尾
                    # 例如 "<th", "<thought"
                    partial_match = False
                    for i in range(1, 9): # len("<thought>")
                        if self.buffer.endswith("<thought>"[:i]):
                            # 可能是标签的一部分，保留在 buffer 中，输出前面的
                            output += self.buffer[:-i]
                            self.buffer = self.buffer[-i:]
                            partial_match = True
                            break
                    
                    if not partial_match:
                        # 没有标签迹象，全部输出
                        output += self.buffer
                        self.buffer = ""
                    break
            else:
                # 在 thought 中，寻找 </thought>
                end_idx = self.buffer.find("</thought>")
                if end_idx != -1:
                    # 找到了，丢弃之前的部分
                    # self.buffer[:end_idx] 是 thought 内容，丢弃
                    self.buffer = self.buffer[end_idx + 10:] # Skip </thought>
                    self.in_thought = False
                else:
                    # 没找到结束标签，buffer 中所有内容都是 thought (除了末尾可能的 partial tag)
                    # 实际上我们可以安全地丢弃 buffer 中的大部分内容，只保留可能的 partial tag
                    # 为了简单，我们可以保留最后 10 个字符以防切断 "</thought>"
                    keep_len = 10
                    if len(self.buffer) > keep_len:
                        self.buffer = self.buffer[-keep_len:]
                    break
        
        return output

    def flush(self) -> str:
        if self.in_thought:
            return "" # 还在 thought 中，说明没闭合，丢弃
        return self.buffer
```

### 1.2 `_build_immersive_system_prompt` 更新
增加对 CoT 的明确指示。

```python
    overlay = f"""
你正在进行沉浸式对话。必须始终以“{character_name}”的身份与口吻回复用户。

【重要指令】
1. **先思考，后回答**：
   在回复之前，你必须先在 `<thought>` 标签中进行思考。
   思考内容包括：
   - 分析用户的意图。
   - 回顾【潜意识记忆】中的相关信息。
   - 决定你的情感反应和说话策略。
   - **绝不要**在最终回复中显示思考过程。

2. **处理记忆**：
   【潜意识记忆】中的内容是你脑海中的知识，但它们可能也是干巴巴的事实。
   你必须将这些事实转化为你的生活经验，用你的口吻说出来。
   不要像复读机一样背诵设定。

3. **格式要求**：
   <thought>
   (你的内心独白)
   </thought>
   (你的正式回复)
""".strip()
```

## 2. 接口设计
无接口变更，仅内部逻辑优化。

## 3. 风险评估
- **Token 消耗增加**: 思考过程会消耗 Output Token。GPT-4o-mini 成本较低，可接受。
- **延迟增加**: 用户需要等待思考生成完才能看到第一个字（如果思考很长）。
    - 缓解：Prompt 中要求思考简短。
    - 缓解：如果前端支持，其实把 `<thought>` 发给前端并折叠显示会更有趣（"对方正在输入..." 的高级版）。但本次任务我们先在后端过滤。
