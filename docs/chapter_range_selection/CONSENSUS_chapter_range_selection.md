# CONSENSUS_chapter_range_selection

## 1. 需求描述
用户希望在开始文档处理任务时，能够选择处理的章节范围，而不是默认处理所有剩余章节。这对于分批处理大型文档或重新处理特定章节非常有用。

## 2. 验收标准
1.  **UI 交互**:
    - 在点击文档的 "开始构建" 或 "继续任务" 按钮时，弹出一个模态框 (Modal)。
    - 模态框显示文档总章节数。
    - 提供 "开始章节" 和 "结束章节" 输入框。
        - 默认 "开始章节" 为 `当前已处理章节 + 1` (如果是 0 则为 1)。
        - 默认 "结束章节" 为 `总章节数`。
    - 点击模态框的 "确定" 按钮后，触发构建任务。
2.  **API 功能**:
    - `POST /novels/{id}/documents/{doc_id}/build/start` 接口支持接收 `start_chapter` (int) 和 `end_chapter` (int) 参数。
    - 参数为可选，如果不传则保持原有行为 (从断点继续到结束)。
3.  **后端逻辑**:
    - `run_indexing_task` 能够接收指定的范围，并只处理该范围内的章节。
    - 进度更新逻辑：处理过程中实时更新 `processed_chapters` 为当前正在处理的章节号。

## 3. 技术方案
### 3.1 前端 (React)
- 修改 `Daisy_brain/web/src/pages/Library.jsx`。
- 引入 `Modal`, `InputNumber` 组件。
- 新增 `buildModalVisible`, `buildRange` (`start`, `end`) 等状态。
- 修改 `handleStartDocBuild` 和 `handleResumeDocBuild` 逻辑，改为打开 Modal。
- 新增 `handleConfirmBuild` 函数调用 API。
- 修改 `src/api/novel.js` 中的 `startDocumentBuild` 方法以支持参数。

### 3.2 后端 (FastAPI)
- 修改 `Daisy_brain/src/api/novels.py`。
- 定义 `StartBuildRequest` Pydantic 模型。
- 更新 `start_document_build` 签名以接收 Body。
- 更新 `run_indexing_task` 签名及内部循环逻辑。

## 4. 技术约束
- 章节号从 1 开始计数 (UI 和 API 参数)。
- 后端 Python 列表索引从 0 开始，需要进行 -1 转换。
- `processed_chapters` 字段将反映最近一次任务的进度位置。

## 5. 风险与缓解
- **进度覆盖风险**: 如果用户重处理旧章节，进度条会"倒退"。
    - **缓解**: 这是符合预期的行为，因为进度条指示的是 "下一次默认从哪里开始"。
- **并发冲突**: 同一文档不允许多个任务并行。
    - **缓解**: 现有逻辑已有 `doc.status == 'processing'` 检查，维持不变。

