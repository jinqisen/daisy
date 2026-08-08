# 对齐文档：Prompt 合并优化方案

## 1. 需求理解
用户提到的 "promote合并优化" 推测为 **"Prompt 合并优化"**。
当前系统在生成最终回复前，会先调用一次 LLM (Prompt Engineer Agent) 来生成 CO-STAR 格式的 System Prompt，然后再调用一次 LLM 生成最终回复。
这是一个典型的优化点：可以通过**模板化**直接构建 System Prompt，从而减少一次昂贵的 LLM 调用。

## 2. 现状分析 (As-Is)
当前流程：
1.  **数据准备**: 收集画像、风格、内心独白、历史记录。
2.  **Meta-Prompting (LLM Call)**: 调用 LLM，输入上述数据，要求它"扮演 Prompt 工程师"，输出一段结构化的 CO-STAR System Prompt。
3.  **Final Generation (LLM Call)**: 将上一步生成的 System Prompt 喂给 LLM，生成最终回复。

**缺点**:
- **延迟高**: 串行多了一次 LLM 调用。
- **成本高**: 双倍的 Token 消耗。
- **不可控**: 中间层 LLM 可能会幻觉或遗漏关键约束。

## 3. 优化方案 (To-Be)
目标流程：
1.  **数据准备**: 同上。
2.  **Template Assembly (Local)**: 使用 Python 字符串模板，直接将数据填入预定义的 CO-STAR 结构中。
3.  **Final Generation (LLM Call)**: 直接使用组装好的 System Prompt 生成回复。

### 核心变更点
- 移除 `_generate_costar_instruction` 中的 LLM 调用。
- 重构 `get_costar_prompt`，使其直接返回最终可用的 System Prompt，而不是 Meta-Prompt。

## 4. 预定义模板结构 (Draft)

```markdown
# Role Description
[角色画像]

# Context & History
[历史记录与当前情境]

# Style & Persona
[风格分析结果]

# Inner Thoughts (Context Only)
[内心独白]

# Task (CO-STAR Framework)
- **C (Context)**: See above.
- **O (Objective)**: Respond to user input naturally based on your persona.
- **S (Style)**: Follow the Style section strictly.
- **T (Tone)**: Use the tone from your Inner Thoughts but formatted for social context.
- **A (Audience)**: User is your friend/partner.
- **R (Response)**: Keep it short, natural, spoken language.
```

## 5. 预期收益
- **延迟**: 降低约 30%-50% (取决于模型速度)。
- **成本**: 每次对话减少 1 次 LLM 输入输出费用。
- **质量**: 响应更加稳定，避免了 Prompt Engineer 的过度解读。

## 6. 确认
请确认是否立即执行此优化方案。
