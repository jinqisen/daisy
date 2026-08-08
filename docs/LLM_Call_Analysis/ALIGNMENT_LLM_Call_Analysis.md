# 任务：分析每次响应客户对话的大模型调用情况

## 1. 项目上下文分析

Daisy_Demo 是一个基于 "Daisy" 架构的 AI 伴侣系统。后端 `Daisy_server` 使用 FastAPI 和 LangGraph 构建了一个复杂的对话处理工作流。前端 `Daisy_front` 是一个 React 应用。

核心对话逻辑位于 `Daisy_server/app/workflow/graph.py` 定义的 LangGraph 图中。每次用户请求 (`/chat` 端点) 都会触发一次图的执行。

## 2. LLM 调用流程详细分析

系统使用 LangGraph 协调多个处理节点，大部分节点涉及 LLM 调用。以下是按执行顺序的详细细分：

### 2.1. 情感分析 (`analyze_emotion`)
- **位置**: `app/workflow/nodes/emotion.py` -> `app/services/emotion.py`
- **逻辑**:
  - 主要使用本地 Transformer 模型 (GoEmotions) 进行分类。
  - **LLM 调用 (条件)**: 如果输入是中文 (`is_chinese(text)` 为真)，会调用 LLM 将文本翻译为英文以供模型分析。
- **调用次数**: 0 或 1 次。

### 2.2. 并行处理分支

情感分析后，系统并行执行以下分支：

#### A. 记忆检索 (`retrieve_memory`)
- **位置**: `app/workflow/nodes/memory.py`
- **逻辑**:
  - **LLM 调用 (条件)**: 如果输入较长或复杂 (`should_use_llm` 为真)，调用 LLM 生成优化的搜索查询 (`get_memory_search_query_prompt`)。
  - 否则直接使用用户输入。
- **调用次数**: 0 或 1 次。

#### B. 沟通风格分析 (`analyze_communication_style`)
- **位置**: `app/workflow/nodes/strategy.py` -> `app/services/strategy_service.py`
- **逻辑**:
  - 默认使用 `LLMStrategy`。
  - **LLM 调用 (缓存)**: 调用 LLM 根据上下文和情感选择最佳人格策略 (`get_strategy_selection_prompt`)。
  - 结果会被 Redis 缓存 (TTL 1小时)。
- **调用次数**: 0 或 1 次 (取决于缓存命中)。

#### C. 话题总结 (`summarize_topic`)
- **位置**: `app/workflow/nodes/generation.py` -> `app/services/topic_agent.py`
- **逻辑**:
  - **LLM 调用 (缓存)**: 调用 LLM 总结最近的对话历史 (`get_topic_summary_prompt`)。
  - 结果会被 Redis 缓存 (TTL 10分钟)。
- **调用次数**: 0 或 1 次 (取决于缓存命中)。

#### D. 确保画像 (`ensure_portrait`)
- **位置**: `app/workflow/nodes/generation.py` -> `app/services/generation.py`
- **逻辑**:
  - **LLM 调用 (条件)**: 如果数据库中没有当前角色的画像 (`common.portrait`)，调用 LLM 生成画像。
  - 一旦生成并保存，后续请求不再调用。
- **调用次数**: 0 或 1 次 (通常为 0，仅在首次交互时调用)。

### 2.3. 响应生成 (`generate_response`)
- **位置**: `app/workflow/nodes/generation.py`
- **逻辑**: 这是一个汇聚节点，包含多个内部步骤：

  1.  **语言风格分析 (Task 2)**:
      - `generate_style_analysis` -> `app/services/generation.py`
      - **LLM 调用 (缓存)**: 分析当前混合人格的语言风格。
      - 结果被 Redis 缓存。
      - **调用次数**: 0 或 1 次。

  2.  **角色内心独白 (Task 3)**:
      - `generate_agent_thoughts` -> `app/crew/service.py` (CrewAI)
      - **LLM 调用**: 为每个活跃的人格 (Active Persona) 启动一个 Agent 进行思考。
      - 活跃人格数量通常为 1-3 个 (权重 > 15%)。
      - **调用次数**: 1 到 3 次。

  3.  **CO-STAR 指令生成 (Task 5)**:
      - `_generate_costar_instruction`
      - **LLM 调用**: 将前面所有任务 (画像、风格、独白、历史) 整合，生成给最终模型的 Prompt。
      - **调用次数**: 1 次。

  4.  **最终回复生成**:
      - `_generate_final_llm_response`
      - **LLM 调用**: 使用 CO-STAR 指令和完整上下文生成最终回复。
      - **调用次数**: 1 次。

## 3. 调用统计总结

| 步骤 | 场景 | 最小调用数 (缓存命中/简单输入) | 典型调用数 | 最大调用数 (冷启动/复杂输入) |
| :--- | :--- | :---: | :---: | :---: |
| 1. 情感分析 | 中文翻译 | 0 (非中文) | 1 (中文) | 1 |
| 2. 记忆检索 | 查询优化 | 0 (短文本) | 0 | 1 |
| 3. 沟通风格 | 策略选择 | 0 (缓存) | 1 | 1 |
| 4. 话题总结 | 历史摘要 | 0 (缓存) | 1 | 1 |
| 5. 确保画像 | 画像生成 | 0 (已存在) | 0 | 1 |
| 6. 风格分析 | 语言风格 | 0 (缓存) | 1 | 1 |
| 7. 内心独白 | CrewAI | 1 (1个活跃人格) | 1-2 | 3 |
| 8. 指令生成 | CO-STAR | 1 | 1 | 1 |
| 9. 最终回复 | Final Gen | 1 | 1 | 1 |
| **总计** | | **3 次** | **7-8 次** | **11 次** |

## 4. 结论

每次响应客户对话，系统会进行 **3 到 11 次** LLM 调用。

- **最少情况 (3次)**: 非中文短文本，且所有缓存 (风格、话题、策略) 均命中，仅 1 个活跃人格。
  - CrewAI (1) + CO-STAR (1) + Final (1) = 3
- **典型情况 (约 7 次)**: 中文输入，部分缓存失效，1-2 个活跃人格。
  - Translation (1) + Strategy (1) + Topic (1) + Style (1) + CrewAI (1) + CO-STAR (1) + Final (1) = 7
- **最大情况 (11次)**: 冷启动，所有缓存失效，中文长文本，3 个活跃人格。

**优化建议 (可选)**:
- 增加缓存 TTL。
- 合并部分 LLM 调用 (例如 CO-STAR 生成可以与最终回复合并，但这会降低可控性)。
- 减少 CrewAI 的活跃人格数量。
