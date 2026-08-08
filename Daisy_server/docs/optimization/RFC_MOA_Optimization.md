# RFC: 基于 MOA (Multi-Objective Alignment) 的角色扮演优化方案

## 1. 背景与启发
用户提供了论文 [arXiv:2512.09756](https://arxiv.org/abs/2512.09756) **"MOA: Multi-Objective Alignment for Role-Playing Agents"**。
该论文提出了一种通过强化学习（RL）同时优化多个细粒度评分标准（Rubrics）的框架，解决了角色扮演 Agent (RPA) 在**指令遵循**、**领域知识**和**语言风格**之间难以平衡的问题。

### 1.1 论文核心洞察 (Insights)
1.  **多目标冲突 (Objective Conflict)**: RPA 需要同时满足多个可能冲突的目标（例如：既要“说话像个文盲混混”，又要“准确回答量子物理问题”）。传统的单目标优化（如只看回复质量）往往顾此失彼。
2.  **细粒度评分标准 (Fine-grained Rubrics)**: 仅仅给一个笼统的 Persona 是不够的。MOA 引入了具体的评分维度（如“风格一致性”、“知识准确性”、“对话连贯性”），并针对每个维度进行优化。
3.  **思维增强 (Thought Augmentation)**: 通过生成思维链（CoT）并利用 Off-Policy 引导，可以显著提升模型处理复杂指令的能力和输出的多样性。

### 1.2 对 Daisy 项目的差距分析
Daisy 当前是一个基于 LLM API 的应用层项目，主要依赖 **Prompt Engineering** (CO-STAR) 和 **Rule-based Logic** (DEP)。
我们无法直接应用 MOA 的 *训练* 方法（RLHF/PPO），但可以将其核心思想转化为 *推理期 (Inference-time)* 的工程方案。

| 维度 | MOA (训练侧) | Daisy 现状 (应用侧) | 优化机会 (Inference-Time Alignment) |
| :--- | :--- | :--- | :--- |
| **目标管理** | 多目标 RL 优化 | CO-STAR Prompt 混合指令 | **引入“动态优先级仲裁”机制** |
| **质量控制** | 基于 Rubric 的 Reward Model | 依赖 LLM 自身能力 | **引入“基于 Rubric 的 Critic/Refine”流程** |
| **上下文学习** | Thought-Augmented Training Data | 简单的 Context 注入 | **构建“多目标增强的 Few-Shot 示例库”** |

---

## 2. 详细优化方案

我们建议从以下三个层面实施 MOA 的启发：

### 方案 A: 显式多目标思维链 (Explicit Multi-Objective CoT) —— *低成本，高收益*
**原理**: 借鉴 MOA 的 Thought-Augmented，在 DEP (动态情感策略引擎) 的基础上，强制 Agent 在思考阶段显式评估冲突目标。

**实施**:
修改 `agent_thoughts` 节点的 Prompt，要求 Agent 在 `[Thought]` 阶段进行“自我辩论”：
1.  **Style Check**: 我现在的语气符合人设吗？
2.  **Knowledge Check**: 用户问的问题需要专业知识吗？
3.  **Conflict Resolution**: 如果人设是“小白”，但用户问了专业问题，我该如何平衡？（例如：用小白的口吻转述，或者装傻）。

**示例输出**:
```text
[Strategy]: Playful_Teasing
[Rubric_Check]:
- Style: 必须保持傲娇，不能太热情。
- Knowledge: 用户问了编程问题，但我的人设不懂代码。
- Resolution: 我会嘲笑用户居然还要写代码，然后胡乱给个建议，或者让他自己查。
[Thought]: 这家伙又在加班写 bug 吗？真是好笑。我要嘲讽他一下...
```

### 方案 B: 基于 Rubric 的 RAG (Rubric-Guided Few-Shot RAG) —— *中成本，提升稳定性*
**原理**: MOA 证明了针对特定 Rubric 优化数据的有效性。我们可以构建一个高质量的“对话示例库”，并为每个示例打上 Rubric 标签。

**实施**:
1.  **构建示例库**: 收集或编写 50-100 条高质量对话。
2.  **Rubric 标注**: 给每条对话打标（例如：`style_score: 5`, `empathy_score: 3`, `knowledge_score: 1`）。
3.  **动态检索**:
    *   当用户需要情感支持时，检索 `empathy_score` 高的示例作为 Few-Shot 放入 Prompt。
    *   当需要特定风格强化时，检索 `style_score` 高的示例。

### 方案 C: 评论-修正循环 (Critic-Refine Loop) —— *高成本，最高质量*
**原理**: 模拟 MOA 的 Reward Model，在推理时引入一个轻量级的 Critic 模型。

**实施**:
1.  **Generate**: 主模型生成回复。
2.  **Critic**: 一个更小/更快的模型（或主模型自身）根据预定义的 Rubrics 打分。
    *   *Check*: "回复是否包含了 3 个以上的成语？（如果人设是古风）"
    *   *Check*: "是否避免了 AI 味？"
3.  **Refine**: 如果得分低于阈值，要求模型重写。

---

## 3. 推荐实施路线 (Roadmap)

考虑到 Daisy 目前的即时性要求（Real-time Chat），**方案 C** 可能会引入过高的延迟（2x-3x 生成时间）。
我们建议优先实施 **方案 A**，并在未来考虑 **方案 B**。

### Phase 1: 增强型思维链 (Enhanced CoT)
*   **动作**: 升级 `crew/service.py` 中的 Prompt。
*   **内容**: 引入 `[Rubric_Check]` 步骤，让 Agent 在生成回复前先进行多维度自我校准。
*   **预期效果**: 减少“人设崩塌”和“AI 味”，更好地处理知识与人设的冲突。

### Phase 2: 动态优先级仲裁 (Dynamic Priority Arbitration)
*   **动作**: 在 `CommonSettings` 中增加 `priority_mode` 配置。
*   **内容**: 允许用户定义：在当前对话中，是 **Style First** (风格优先，哪怕胡说八道) 还是 **Knowledge First** (知识优先，哪怕稍微 OOC)。
*   **预期效果**: 让用户对 Agent 的行为有更细粒度的控制权。

## 4. 讨论点 (For Discussion)
1.  **延迟容忍度**: 引入思维链会增加 Token 消耗和生成时间，我们是否接受？
2.  **Rubric 定义**: 对于 Daisy 的核心用户，最重要的 3 个评分维度是什么？（建议：有趣性、人设一致性、情感共鸣）。
3.  **RAG 资源**: 我们是否有足够的高质量对话数据来构建 Few-Shot 库？如果没有，是否需要合成数据？

请确认您对以上方案的看法，以便我们决定下一步动作。
