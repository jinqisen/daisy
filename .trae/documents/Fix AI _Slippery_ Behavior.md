# 深度优化：引入 CoT (思维链) 的人格选择工程

您的建议直击要害。旧 Prompt 的问题在于它是一个“黑盒”——输入上下文，直接输出结果，中间缺乏推理过程，导致上下文被忽略。
简单的 Rule Warning (打补丁) 不如 **CoT (Chain of Thought)** 稳健。

我将重构 `Daisy_prompts/strategy/selection.yaml`，引入显式的思维链：

## 1. Prompt 结构重构
不再直接要求 JSON，而是强制模型先进行 **三步推理**：

### Step 1: 交互回溯 (Context Review)
*   **指令**: “分析最近 2 轮对话。AI 上一句话是否回答了用户的问题？还是回避了？用户的最新回复是针对内容的，还是针对 AI 态度的？”
*   **目的**: 强迫模型“看见”上下文中的回避行为（即“滑”的来源）。

### Step 2: 意图解码 (Intent Decoding)
*   **指令**: “分析用户的潜台词。例如：‘你好滑’是在夸奖幽默（Compliment），还是在指责回避（Call-out）？注意：带有‘哈哈’的指责依然是指责。”
*   **目的**: 纠正对“哈哈”的过度关注，识别“笑里藏刀”的负面反馈。

### Step 3: 策略过滤 (Strategy Filtering)
*   **指令**: “基于上述分析进行排除。如果确认为指责/质疑，**排除** Ludus (玩闹)，**优选** Storge (真诚)。”

## 2. 输出格式调整
利用 `strategy_service.py` 的正则解析能力 (`re.search(r'\{.*\}')`)，我们可以让模型先输出文本思考，最后输出 JSON。

**新 Prompt 示例**:
```text
Thinking Process:
1. Context: AI evaded the question "Do you look like her?". User said "You are slippery".
2. Intent: User is calling out the evasion. It's a criticism masked with "Haha".
3. Filter: Ludus is inappropriate for criticism. Switch to Storge.

JSON Output:
{ "best_match": "Storge", ... }
```

这种方式让 Task 2 自己完成“微型话题总结”，从而在不依赖 Task 4 (架构限制) 的情况下，彻底激活传入上下文的作用。
