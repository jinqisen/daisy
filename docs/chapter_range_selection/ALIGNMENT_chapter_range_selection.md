# ALIGNMENT_chapter_range_selection

## 1. 项目上下文分析

### 1.1 项目结构
- **Frontend**: React + Ant Design (`Daisy_brain/web`)
- **Backend**: FastAPI + Python (`Daisy_brain/src`)
- **Core Logic**: LightRAG for document processing (`Daisy_brain/src/core/rag_engine.py`)

### 1.2 现有逻辑
- **前端**: `Library.jsx` 显示文档列表，每个文档有 "开始构建" (Start Build) 按钮。
    - 点击按钮直接调用 `novelApi.startDocumentBuild(novelId, docId)`。
    - 文档卡片上显示的 `span` 标签 (如 "第1-50章") 展示的是**已处理**的章节范围 (`processed_chapters`)。
- **后端**: `src/api/novels.py` -> `start_document_build` -> `run_indexing_task`。
    - `run_indexing_task` 目前逻辑是从 `processed_chapters` (上次处理进度) 开始，一直处理到文件末尾 (`total_chapters`)。
    - 也就是默认行为是 "断点续传" 或 "从头开始" (如果没有处理过)。

## 2. 需求理解确认

### 2.1 原始需求
- 用户输入: "`div` 文档处理任务，增加选择处理章节范围"
- 用户选中了展示已处理章节范围的 UI 组件。
- 核心需求: 在启动文档处理任务时，允许用户指定处理的章节范围 (开始章节 - 结束章节)，而不是只能从当前进度处理到最后。

### 2.2 需求理解
1.  **交互变更**: 点击 "开始构建" (或 "继续任务") 时，不应立即开始，而是弹出一个对话框 (Modal)。
2.  **配置项**: 对话框中包含 "开始章节" 和 "结束章节" 的输入框。
    - 默认值建议:
        - 开始章节: 当前 `processed_chapters + 1` (如果是新任务则为 1)。
        - 结束章节: `total_chapters`。
3.  **API 变更**: `startDocumentBuild` 接口需要支持 `start_chapter` 和 `end_chapter` 参数。
4.  **后端逻辑**: `run_indexing_task` 需要根据传入的范围进行索引，而不是默认逻辑。

### 2.3 边界确认
- **输入验证**: 开始章节必须 >= 1，结束章节必须 <= 总章节数，且 开始 <= 结束。
- **状态影响**: 如果用户选择了中间一段 (例如 10-20)，处理完后 `processed_chapters` 应该如何更新？
    - 现有逻辑似乎是用 `processed_chapters` 记录进度。如果支持跳跃处理或分段处理，简单的 `processed_chapters` 计数可能不足以表达 "1-10已处理, 20-30已处理, 11-19未处理" 的状态。
    - **假设**: 为简化实现，且考虑到 RAG 知识库的一致性，通常是连续处理。用户可能只是想 "处理接下来 50 章" 或者 "重试第 5 章"。
    - **策略**: 暂时不改变数据模型 (只记录 `processed_chapters` 一个数字)。
        - 如果用户选择处理 1-50 (当前进度 0)，处理完后进度变为 50。
        - 如果用户选择处理 51-100 (当前进度 50)，处理完后进度变为 100。
        - 如果用户选择处理 5-10 (当前进度 50)，这是一个 "重处理" 操作。
            - 这种情况下，进度数字可能不需要回退，或者后端需要识别这是 "重做"。
            - 鉴于 `run_indexing_task` 主要是 `rag.initialize_index(content)`，重复调用通常是更新/覆盖或添加。
    - **决策**: 本次任务主要关注 "允许用户指定范围"。后端处理逻辑尽量复用，进度更新逻辑如果用户选择了 "跳过前文" (例如从 10 开始，但 1-9 未处理)，这可能会导致数据不完整。
    - **约束**: 建议限制用户只能选择 "当前进度" 之后的范围，或者 "重新处理" 已有的范围。
    - **修正**: 用户可能只想处理一部分，防止任务时间过长。比如总共 1000 章，一次只处理 100 章。这是最合理的场景。
    - **进度更新**: 如果用户当前进度 0，选择了 1-50。任务完成后，进度更新为 50。
    - 如果用户当前进度 50，选择了 51-100。任务完成后，进度更新为 100。
    - 如果用户跳过？(当前 0，选 51-100)。这在 RAG 构建中通常不推荐，因为上下文可能缺失。但如果只是单纯的文本分块入库，技术上可行。
    - **简化策略**: 允许用户输入范围。后端处理该范围。进度更新逻辑保持 "最大已处理章节数" 或 "当前处理的结束章节" (如果它是连续的)。
    - 查看后端代码 `progress_manager.update_document_progress(doc_id, current_processed, "processing")`。它直接更新 `processed_chapters` 为 `i + 1`。
    - 这意味着如果我处理 51-60，循环 `i` 是 50 到 59。`current_processed` 变为 60。这符合预期。
    - 如果我处理 1-10 (重做)，`current_processed` 会变为 10。这会覆盖之前的进度记录 (比如之前是 100)。**这是一个风险点**。
    - **解决方案**: 更新进度时，应该取 `max(current_processed, existing_processed)` 吗？或者让用户明白这是 "更新进度指针"。
    - 考虑到 `processed_chapters` 既用于显示进度，也用于通过 `range(processed, total)` 决定下一次的默认起点。
    - 如果用户重做 1-10，进度变回 10，下次默认从 11 开始。这似乎逻辑上是通的 (用户可能觉得 11-100 需要基于新的 1-10 重新跑？或者只是想重跑前 10 章)。
    - **为了安全起见**: 我们保持 `processed_chapters` 为 "已处理的最大连续章节号" 的语义可能比较困难。
    - **调整**: `update_document_progress` 应该只在 `new_progress > old_progress` 时更新数值？
    - 不，如果用户确实想重置进度，他们应该使用 "Delete" 或 "Reindex"。
    - 这里我们假设用户主要场景是 **分批处理** (Batch Processing)。即：文件太大，想先跑前 50 章看看效果，或者避免一次跑太久。

## 3. 智能决策策略
- **问题 1**: 如何处理用户输入的范围与当前进度的关系？
    - **决策**: 允许任意范围。但在 UI 上默认填充 `Start = processed + 1`, `End = total`。
    - 后端更新进度时，保留 `processed_chapters` 为 "当前任务结束时的章节号"。如果用户回退处理，进度也会回退，这在逻辑上是可以接受的 (表示后续章节可能需要基于新内容重新验证/处理)。
- **问题 2**: 现有 API 是否支持参数？
    - **决策**: 需要修改 `POST /{id}/documents/{doc_id}/build/start`。目前它只接受 path params。需要改为接受 JSON Body。

## 4. 结论
- 修改前端 `Library.jsx`，增加 "构建设置" Modal。
- 修改后端 `start_document_build` 接口及 `run_indexing_task` 任务函数。
