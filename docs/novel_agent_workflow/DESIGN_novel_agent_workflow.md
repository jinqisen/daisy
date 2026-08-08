# 系统架构设计 (Architect)

## 1. 整体架构图
```mermaid
graph TD
    User[用户] --> UI[Streamlit Interactive UI]
    
    subgraph "Daisy_brain (Core System)"
        UI --> WorkflowMgr[Workflow Manager]
        
        subgraph "Data Ingestion Layer"
            WorkflowMgr --> TextProcessor[Text Processor]
            TextProcessor --> |Clean/Chunk| Chunks[Text Chunks]
        end
        
        subgraph "Knowledge Engine (LightRAG+)"
            Chunks --> LightRAG[LightRAG Service]
            LightRAG --> |Extract| Entities[Entities & Relations]
            LightRAG --> |Extract| Events[Events & Scenes]
            LightRAG --> KG_Store[Graph Store (NetworkX/Neo4j)]
            LightRAG --> Vector_Store[Vector Store (Chroma/Faiss)]
        end
        
        subgraph "Agent Factory Layer"
            WorkflowMgr --> Extractor[Character Extractor Agent]
            Extractor <--> |Global/Local Query| LightRAG
            
            Extractor --> |Generate| BaseProfile[Basic Info & Personality]
            Extractor --> |Mining| DialogueSample[Dialogue Samples]
            Extractor --> |Reasoning| Triggers[Plot Triggers]
            
            BaseProfile & DialogueSample & Triggers --> Assembler[Profile Assembler]
        end
        
        Assembler --> Output[Character Profile (JSON)]
    end
    
    UI --> Editor[JSON Editor]
    Editor <--> Output
    
    UI --> GraphViz[Graph Visualizer]
    GraphViz <--> KG_Store
    
    UI --> ChatTest[Chat Playground]
    ChatTest --> |Load| Output
    ChatTest --> |Retrieve| LightRAG
```

## 2. 模块详细设计

### 2.1 核心数据模型 (Domain Models)

#### 2.1.1 扩展角色档案 (`ExtendedRoleProfile`)
继承自 `Daisy_server` 的 `RoleProfile`，增加深度字段。
```python
class ExtendedRoleProfile(BaseModel):
    # --- 基础复用 ---
    basic_info: CommonSettings  # 姓名, 性别, 年龄, 职业等
    personality: RoleProfile    # 描述, 风格, 约束 (System Prompt用)
    
    # --- 深度抽取新增 ---
    catchphrases: List[str]     # 口头禅/典型句式 (Few-shot)
    inner_voice: str            # 心理活动特征描述
    
    relationships: List[Relationship] # 明确定义的强关系
    
    triggers: List[PlotTrigger] # 剧情触发器
    
    # --- 元数据 ---
    source_novel: str
    version: str
```

#### 2.1.2 剧情触发器 (`PlotTrigger`)
```python
class PlotTrigger(BaseModel):
    slug: str                   # 唯一标识 (e.g., "mention_mother")
    condition_desc: str         # 自然语言条件 (e.g., "当用户提到角色的母亲时")
    action_desc: str            # 自然语言反应 (e.g., "表现出极度的悲伤并试图转移话题")
    emotion_shift: Optional[str] # 情绪变化 (e.g., "Sadness")
    quote_reference: Optional[str] # 原文依据
```

#### 2.1.3 事件节点 (`EventNode` - Graph)
在 LightRAG 中存储的特殊实体类型。
-   **Type**: "EVENT"
-   **Properties**:
    -   `summary`: 事件摘要
    -   `participants`: [RoleA, RoleB...]
    -   `location`: 地点
    -   `time_order`: 序号 (用于排序)
    -   `significance`: 重要性评分 (1-10)

### 2.2 核心服务接口 (Service Interfaces)

#### 2.2.1 `LightRAGManager`
负责封装 LightRAG 的复杂操作，提供面向业务的接口。
```python
class LightRAGManager:
    def initialize_index(self, novel_path: str): ...
    
    # 核心：支持针对 Event 的特殊抽取 Prompt
    def extract_events(self) -> List[EventNode]: ...
    
    # 混合检索
    def query(self, text: str, mode: str = "hybrid") -> str: ...
    
    # 获取特定角色的子图
    def get_character_subgraph(self, character_name: str) -> GraphData: ...
```

#### 2.2.2 `CharacterExtractorAgent`
负责调用 LLM 和 LightRAG 生成最终档案。
```python
class CharacterExtractorAgent:
    def __init__(self, rag_manager: LightRAGManager, llm: BaseLLM): ...
    
    async def extract_all(self, name: str) -> ExtendedRoleProfile:
        # 1. 基础信息 (Global Query)
        # 2. 性格分析 (Global Query + Psychology Prompts)
        # 3. 口头禅挖掘 (Local Retrieval of Dialogues)
        # 4. 触发器推导 (Event Graph Analysis)
        pass
```

### 2.3 事件知识图谱构建策略
1.  **Prompt Engineering**: 修改 LightRAG 的默认 Entity Extraction Prompt，强制要求识别 "Event" 类型的实体，并提取 `NEXT` (时序) 和 `CAUSED_BY` (因果) 关系。
2.  **Post-Processing**: 在 LightRAG 初步抽取后，运行一个 Python 脚本来"串联"事件。利用小说章节顺序，为 Event 节点添加 `sequence_id`，确保时间线正确。

## 3. 目录结构规划
```
Daisy_brain/
├── data/                   # 存放小说文本和生成的索引
│   ├── novels/
│   └── indices/
├── src/
│   ├── core/
│   │   ├── config.py       # 配置
│   │   ├── models.py       # Pydantic 模型
│   │   └── rag_engine.py   # LightRAG 封装
│   ├── extractors/
│   │   ├── character.py    # 角色抽取逻辑
│   │   ├── events.py       # 事件图谱构建逻辑
│   │   └── prompts.py      # 专用的 Prompt 模板
│   └── utils/
│       ├── text_processing.py
│       └── graph_viz.py
├── ui/
│   ├── Home.py             # Streamlit 入口
│   └── pages/
│       ├── 1_Import.py     # 上传 & 建库
│       ├── 2_Extract.py    # 角色工坊
│       └── 3_Chat.py       # 测试对话
├── requirements.txt
└── main.py                 # 启动脚本
```

## 4. 数据流向设计 (Data Flow)
1.  **Ingest**: `User Upload` -> `txt` -> `LightRAG Indexing` -> `Graph/Vector DB`.
2.  **Extract**: `User Select Name` -> `Extractor` -> `Query RAG (Events/Traits)` -> `LLM Synthesis` -> `JSON Profile`.
3.  **Refine**: `JSON Profile` -> `UI Editor` -> `User Edit` -> `Saved JSON`.
4.  **Chat**: `User Msg` -> `Chat Engine` -> `Retrieve (Vector+Graph)` + `System Prompt (Profile)` -> `Response`.

## 5. 关键技术难点与对策
-   **难点**: 事件的时序性错乱。
    -   **对策**: 在分块（Chunking）时保留章节元数据。在构建 Event 节点时，强制将章节 ID 作为属性写入，图查询时按章节 ID 排序。
-   **难点**: 触发器抽取过于抽象。
    -   **对策**: 采用 "Few-shot" 策略。在 Prompt 中提供 3 个高质量的 "条件-反应" 示例（如林黛玉的"落花-悲伤"），引导 LLM 模仿格式输出。
