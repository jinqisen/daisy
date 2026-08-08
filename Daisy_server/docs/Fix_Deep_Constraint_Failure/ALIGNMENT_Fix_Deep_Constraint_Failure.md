# ALIGNMENT_Fix_Deep_Constraint_Failure

## 1. 原始需求 (多轮对话失效)
用户提供了进一步的对话记录，显示即使有了异地约束，AI 在多轮对话的“激将法”攻势下依然破防，甚至升级了行为：
1.  **用户**: “那我真不信”
2.  **AI (Daisy)**: “行，那咱们打个赌？下周四晚上七点，江滩公园老渡口，我要是真出现了，你得答应我一件事。”

**分析**:
这表明简单的 System Prompt 静态约束在面对连续的、针对性的上下文（Contextual Pressure）时失效了。AI 陷入了“赌约”的逻辑陷阱，为了赢得赌约，必须坚持“我会出现”，从而彻底违背了“异地无法见面”的底层设定。

## 2. 根因分析
1.  **System Prompt vs. Recent History**: LLM 往往更关注最近的对话历史 (Recency Bias)。当最近几轮对话都在讨论“能不能来”、“信不信”时，AI 的注意力被锁定在这个局部冲突上，遗忘了 System Prompt 中的全局约束。
2.  **逻辑连贯性陷阱**: 上一轮 AI 已经说了“见呗”（这是第一次破防），为了保持逻辑连贯（Self-Consistency），这一轮它必须继续圆谎，甚至加码（打赌）。
3.  **情绪/意图优先级**: AI 可能将“好胜心”、“调情”、“拉扯”的优先级排在了“物理事实”之上。

## 3. 解决方案策略
仅靠修改静态的 System Prompt (如上一轮所做) 已经不够了，因为历史记录中的错误示范（上一轮的“见呗”）具有很强的误导性。

我们需要引入 **Runtime Guardrails (运行时护栏)** 或 **Dynamic Prompt Injection (动态提示注入)**。

### 方案 A: 增强型 System Prompt (低成本，快速尝试)
在 System Prompt 的**最后**（Recency Effect）再次强调约束，并明确指示“如果之前的对话中我不小心答应了见面，请立即用开玩笑的方式找补回来，而不是继续错误”。

### 方案 B: 动态思维链 (Thought-Process Injection)
修改 `app/workflow/nodes/generation.py`，在生成回复前的 `Thought` 阶段，强制插入一个检查步骤：
`Check: Does my response violate the 'Long-distance' constraint?`

### 方案 C: 后处理/拦截 (Post-Processing)
检测回复中是否包含具体的见面邀约（时间+地点），如果包含且不仅是幻想，则重写回复。

## 4. 推荐实施方案 (方案 A + B)
鉴于 Daisy 目前架构，方案 B (修改生成节点的 Prompt) 是最自然且有效的。

### 4.1 修改 `generation.py` 的 Prompt 结构
在构建 `messages` 时，不仅仅依赖 System Prompt，而是在 User Message (Context) 的末尾追加 **Critical Instruction**。

**当前结构**:
```python
system_message = ...
user_message = context + history
```

**优化后结构**:
```python
system_message = ...
user_message = context + history + "\n\n[系统监控]: 检测到话题涉及线下见面。请务必记住你们是异地，绝对无法见面。如果上一句你不小心答应了，请立刻用开玩笑的方式反转（例如：'骗你的啦，我怎么可能飞过去'）。不要继续编造谎言。"
```

## 5. 待办事项
1.  定位 `app/workflow/nodes/generation.py` 或相关生成逻辑。
2.  分析如何检测话题（关键词匹配：见面、过来、江滩、地址、时间）。
3.  如果检测到敏感话题，动态注入强提醒。
