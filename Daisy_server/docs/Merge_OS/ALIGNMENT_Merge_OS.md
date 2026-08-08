# ALIGNMENT_Merge_OS: 多人格内心OS融合优化

## 1. 项目上下文分析
- **现有逻辑**:
  - `agent_thoughts` 节点并发调用多个活跃人格（Active Personas）生成各自独立的内心独白（Thoughts）。
  - `generate_response` 节点将这些独白简单拼接（`[Persona A]: Thought A\n[Persona B]: Thought B`）后放入 Context 提交给最终回复模型。
- **问题**:
  - 缺乏“融合”过程：系统简单罗列了不同人格的想法，而没有模拟出一个“复杂大脑”如何权衡这些冲突声音的过程。
  - 权重利用不足：虽然生成 Prompt 时带上了权重标签，但最终模型可能倾向于只听从第一个或最长的一个，缺乏按比例融合的细腻度。
  - 缺乏复杂性：真正的多重人格融合应该表现为“主人格的纠结”或“潜意识的干扰”，而不是两个分开的人在说话。

## 2. 需求理解确认
- **原始需求**: "汇总...是不是应该按照人格比例融合不同人格的内心os...增加复杂性"。
- **核心目标**: 在最终回复之前，增加一个**“思维融合 (Thought Synthesis)”**的机制，根据人格权重将分散的独白整合成一个统一但复杂的内心流。

## 3. 智能决策策略 (方案分析)

### 方案 A: 独立融合节点 (Independent Synthesis Node)
- **描述**: 在 `agent_thoughts` 之后增加一次 LLM 调用，专门负责将 `List[Thoughts]` 融合为 `String (Final OS)`。
- **优点**: 
  - 输出清晰，UI 可以展示“融合后的最终想法”。
  - 融合逻辑可控，可以强制要求体现“70% A + 30% B”的纠结感。
- **缺点**: 
  - 增加延迟 (Extra LLM Call)。

### 方案 B: 在最终生成中通过 Prompt 引导融合 (Prompt-Guided Synthesis in Final Gen)
- **描述**: 修改 `generate_response` 的 Prompt 结构，要求最终模型先输出 `[Synthesized Thought]`，再输出 `[Response]`。
- **优点**: 
  - 零额外延迟（利用最终生成的 Token 输出思维链）。
  - 上下文连贯。
- **缺点**: 
  - 如果最终模型遵循指令能力不强，可能跳过融合直接回答。

### 推荐方案: 方案 B+ (结构化思维链)
鉴于项目对延迟敏感 (参考 `Optimization_Response_Time_v2`)，我们应尽量避免增加串行 LLM 调用。
建议在 **Final Response Prompt** 中引入明确的 **Synthesis Step**。

## 4. 关键决策点 (待确认)
- **确认**: 是否同意使用 **方案 B+** (修改最终生成 Prompt，让模型在生成回复前先输出融合后的 OS)，以避免增加额外的 API 调用延迟？
- 或者，如果您非常看重“融合后OS”的独立存档/展示价值，我们可以选择 **方案 A**。

## 5. 拟定规范 (基于方案 B+)

### 修改 `app/workflow/nodes/generation.py` -> `_format_task_outputs`
- 不再只是简单拼接，而是构建一个结构化的 Prompt 块：
  ```text
  ### Task 3: Conflicting Inner Voices (Raw Data)
  The following are raw thoughts from your different personality facets. 
  Please synthesize them based on their influence weights.
  
  - Facet: [Name A] (Weight: 0.7)
    Thought: ...
  - Facet: [Name B] (Weight: 0.3)
    Thought: ...
  ```

### 修改 `app/prompts/templates.py` -> `get_costar_prompt` (或相关 Final Prompt)
- 增加指令：
  ```text
  **Step 1: Thought Synthesis**
  Review the "Conflicting Inner Voices". 
  Generate a "Final Internal Monologue" that blends these voices. 
  - Dominant facet (0.7) should drive the main intent.
  - Minor facet (0.3) should add nuance, hesitation, or emotional coloring.
  - Output format: [Final OS]: ...
  
  **Step 2: Response Generation**
  Based on the "Final Internal Monologue", generate the response to the user.
  ```

## 6. 下一步计划
1.  用户确认方案。
2.  创建 CONSENSUS 文档。
3.  执行代码修改。
