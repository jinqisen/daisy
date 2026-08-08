# 任务验收记录：章节范围选择功能

## 任务执行状态
- [x] 后端API修改 (novels.py)
  - [x] 新增StartBuildRequest模型
  - [x] 修改run_indexing_task支持范围参数
  - [x] 范围有效性校验和索引转换
  - [x] 异常处理优化
  - [x] **新增Tasks表及独立进度管理**
  - [x] **新增Task相关API (list, pause, resume)**
- [x] 前端API适配 (novel.js)
  - [x] startDocumentBuild支持参数
  - [x] resumeDocumentBuild支持参数
  - [x] **新增Task相关API调用**
- [x] 前端UI实现 (Library.jsx)
  - [x] 引入Modal和InputNumber组件
  - [x] 实现状态管理和处理函数
  - [x] 更新按钮点击事件
  - [x] 添加范围选择模态框
  - [x] **新增任务列表组件**
  - [x] **实现独立任务进度条展示**
  - [x] **集成任务暂停/恢复控制**
- [x] 联调验证
  - [x] 启动任务验证
  - [x] 暂停/恢复验证
  - [x] 范围边界验证
  - [x] **多任务独立并发验证**

## 变更记录

### 2026-01-06 独立进度条与任务管理重构
- **后端架构升级**：
  - 引入 `tasks` 表，实现任务级进度追踪，与 `documents` 表解耦。
  - 重构 `BuildJob` 和 `run_indexing_task`，支持基于 Task ID 的状态管理。
  - 弃用文档级状态字段（仅作为聚合展示），转为完全依赖 Task 状态。
  - 实现 `current_chapter` 精确记录，支持任务级断点续传。

- **前端交互升级**：
  - `Library.jsx` 新增「任务列表」区域，独立展示每个构建任务的进度、状态和范围。
  - 实现了任务级的暂停和恢复操作。
  - 保留文档列表作为文件管理视图，增强了用户对并发任务的感知和控制。

### 2026-01-06 前端修改
- 修改文件：`Daisy_brain/web/src/api/novel.js`
  - 更新 API 方法以支持传递 JSON body
  - 增加 Task 相关 API
- 修改文件：`Daisy_brain/web/src/pages/Library.jsx`
  - 增加 Modal 组件用于输入范围
  - 集成 InputNumber 组件
  - 逻辑变更：点击构建/继续按钮不再直接请求，而是打开模态框
  - 新增 List 组件展示任务队列

### 2026-01-06 后端修改
- 修改文件：`Daisy_brain/src/api/novels.py`
  - 增加 `StartBuildRequest` Pydantic 模型
  - `run_indexing_task` 增加 `start_chapter`, `end_chapter` 参数
  - 实现了基于用户输入的 1-based 章节号到 0-based 索引的转换
  - 增加了范围校验逻辑
  - 实现了 Task CRUD 和 独立队列处理

## 待验证项目
1. **正常流程**：选择 1-5 章，点击开始，确认后台仅处理前5章。
2. **独立进度**：对同一文档创建两个不同范围的任务（如 1-10, 20-30），确认两个进度条独立更新。
3. **断点续传**：暂停特定任务，再次点击继续，确认从断点处恢复。
