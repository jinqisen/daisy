# 项目共识文档 (Consensus)

## 1. 核心目标
构建一个 **"小说 -> 智能体" 的转化工厂 (`Daisy_brain`)**。该系统能从小说文本中自动化抽取深度角色档案（包括人格、记忆、行为逻辑），构建基于 **事件知识图谱 (Event Knowledge Graph)** 的 RAG 知识库，最终生成可用于角色扮演的 AI 智能体配置。

## 2. 需求与规范

### 2.1 输入输出
-   **Input**: 小说文本文件 (.txt)。
-   **Output**: 
    -   角色配置文件 (`CharacterProfile.json`): 包含基础信息、性格、口头禅、触发器。
    -   角色知识库 (`LightRAG Index`): 包含实体、关系、事件图谱和向量索引。
    -   前端展示: 抽取进度、知识图谱可视化、角色对话测试窗口。

### 2.2 核心功能模块
1.  **Deep Extraction Pipeline (深度抽取流水线)**:
    -   **Entity & Relation**: 人物、地点、物品及其关系。
    -   **Event & Scene**: 关键事件、场景、时序关系。
    -   **Psychology & Dialogue**: 心理活动链、口头禅样本。
    -   **Triggers**: "Condition -> Action" 行为触发器。
2.  **Hybrid RAG Engine (混合检索引擎)**:
    -   结合 **LightRAG** (图检索) 和 **Vector RAG** (语义检索)。
    -   支持 "Global Query" (宏观总结) 和 "Local Query" (细节追溯)。
3.  **Interactive Workbench (交互式工坊)**:
    -   基于 Streamlit 的 UI。
    -   支持人机协作 (Human-in-the-Loop): 自动生成初稿 -> 人工修正 -> 验证测试。

### 2.3 技术约束
-   **Environment**: Windows, Python 3.10+。
-   **Core Libs**: `lightrag-hku` (知识图谱), `streamlit` (UI), `openai`/`langchain` (LLM 调用)。
-   **Storage**: 本地文件系统 (JSON, GraphML, Vector DB files)。

## 3. 验收标准
1.  **完整性**: 能成功从一本中篇小说中抽取主要角色的完整档案，包含不少于 5 个关键事件和 3 个触发器。
2.  **准确性**: 抽取的性格描述与原著基本符合，口头禅有原著特色。
3.  **可交互**: 用户能在 UI 上看到知识图谱，并能修正生成的 JSON。
4.  **RAG 效果**: 在对话测试中，角色能正确回忆起知识库中的特定事件。
