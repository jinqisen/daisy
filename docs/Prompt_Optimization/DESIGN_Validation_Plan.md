# 方案验证：Prompt 优化对比与 CrewAI 合并

## 1. 任务范围

本任务旨在验证“Prompt 合并优化”方案的有效性，并探索进一步压缩 LLM 调用的可能性（合并内心独白）。

## 2. 验证计划 (A/B 测试)

我们将创建一个独立的测试脚本 `scripts/test_prompt_optimization.py`，模拟生成节点的关键逻辑。

### 测试用例
- **场景**: 用户输入“我今天工作很累，感觉没人在乎我。”
- **变量**:
    - **Control (组A)**: 现有逻辑 (Meta-Prompting -> Final Gen)。
    - **Treatment (组B)**: 优化逻辑 (Template Assembly -> Final Gen)。
- **评估指标**:
    - **耗时**: 两个步骤的总耗时。
    - **Token**: 估算 Token 消耗差异。
    - **质量**: 最终输出的主观质量对比（是否丢失了约束或风格）。

### 测试脚本结构
1.  **Mock Data**: 准备固定的画像、风格分析、内心独白、历史记录。
2.  **Function A (Current)**: 复刻 `_generate_costar_instruction` + `_generate_final_llm_response`。
3.  **Function B (New)**: 实现基于模板的 `generate_costar_prompt_template` + `_generate_final_llm_response`。
4.  **Runner**: 并行或串行运行 A 和 B，打印结果和指标。

## 3. CrewAI (内心独白) 合并可行性分析

用户提问：“内心独白能够合并到一次复杂智能体吗？”

### 现状
-   `generate_agent_thoughts` 调用 `CrewAI`。
-   如果有 3 个活跃人格 (例如 Eros, Ludus, Pragma)，CrewAI 可能会：
    -   启动 3 个 Agent。
    -   产生多次 LLM 交互（取决于 Process 是 Sequential 还是 Hierarchical，以及 CrewAI 的内部实现）。
    -   即使是并行，也是 3 次独立的请求。

### 合并方案 (Chain-of-Thought Integration)
我们可以将“内心独白”作为最终生成 Prompt 的一部分 **思维链 (Chain of Thought)**，而不是作为前置任务。

**方案 C (极致合并)**:
-   **不再预先调用 CrewAI**。
-   **System Prompt 修改**:
    -   在 CO-STAR 的 Instruction 中，要求模型 **先输出内心独白**，再输出回复。
    -   格式示例：
        ```
        <thought>
        [Eros]: 看到他这么累，我好心疼，想抱抱他。
        [Ludus]: 别太沉重，逗他笑一下。
        </thought>
        <response>
        亲爱的，快过来抱抱！（揉揉头）今晚不仅有我，还有你最爱的冰淇淋哦，是不是瞬间复活啦？
        </response>
        ```

**优势**:
-   调用次数从 **(1~3 CrewAI + 1 Prompt + 1 Final) = 3~5 次** 降低为 **1 次**。
-   模型可以在生成回复时直接利用即时的思维链，逻辑更连贯。

**劣势**:
-   **可控性降低**: 无法像 CrewAI 那样为每个人格设定严格独立的 Prompt 和 Backstory。
-   **上下文窗口**: Prompt 会变长。

### 结论
本次测试将包含 **方案 C (One-Shot CoT)** 的原型验证。

## 4. 交付物
1.  `scripts/test_prompt_optimization.py`: 包含 A/B/C 三种模式的测试代码。
2.  执行报告：展示三种模式的效果对比。
