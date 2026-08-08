# 任务：将右侧分析面板移动到抽屉

## 1. 需求理解
用户希望将前端界面中，位于对话框右侧的所有图表和分析内容（Analysis Dashboard）移动到一个右侧抽屉（Drawer）中。
默认情况下，这个抽屉应该是收起（关闭）的，无论登录账号是什么类型（普通用户或超级用户）。

## 2. 现有架构分析
- **文件**: `Daisy_front/src/App.tsx`
- **布局**: 目前使用 Ant Design 的 `Row` 和 `Col` 布局。
    - 左侧 (`Col flex="3"`): `ChatInterface`
    - 右侧 (`Col flex="7"`): 包含 `StateVisualizer`, `CommunicationAnalysisCard`, 以及超级用户可见的图表。
- **状态管理**: `App.tsx` 管理了所有的状态 (`visualState`, `logs`, `isSuperUser` 等) 并传递给子组件。

## 3. 方案设计
### 3.1 布局调整
- 移除原本的左右分栏结构（`Row`/`Col`）。
- `ChatInterface` 将占据主视图的绝大部分空间（或 100%）。
- 引入 `Drawer` 组件，将原本右侧 `Col` 中的内容放入 `Drawer` 中。

### 3.2 交互设计
- **默认状态**: `Drawer` 默认关闭 (`visible={false}` 或 `open={false}`)。
- **触发方式**: 在界面右上角（或悬浮按钮）添加一个图标/按钮，用于打开/关闭抽屉。
    - 建议在 `Header` 的右侧，用户头像旁边添加一个“数据面板”或类似图标的按钮。
    - 或者在聊天界面的右上角添加一个悬浮按钮。
    - 考虑到 `Header` 已经存在，且有空间，放在 `Header` 上比较整洁。

### 3.3 组件重构 (Refactoring)
- 为了保持 `App.tsx` 的整洁，建议将原本右侧的内容提取为一个独立的组件 `AnalysisDashboard`。
- `AnalysisDashboard` 将接收所有必要的 props (`visualState`, `logs`, `isSuperUser`, `traceData`, `latestUserMessageId` 等)。

## 4. 关键决策点
- **Q**: 抽屉打开时是覆盖在聊天界面上，还是挤压聊天界面？
  - **A**: Ant Design `Drawer` 默认是覆盖（Overlay）。为了不影响聊天布局的重排，覆盖模式体验较好，也符合“抽屉”的隐喻。
- **Q**: 抽屉的宽度？
  - **A**: 原本右侧占 `flex="7"` (70%)。在抽屉中可能不需要那么宽，或者可以设为宽屏的一半或固定宽度（如 600px）。考虑到图表较多，建议设置较宽的宽度（如 `70vw` 或 `800px`），且允许响应式调整。

## 5. 验收标准
1.  进入页面时，右侧分析面板不可见，聊天界面占据主体。
2.  点击指定按钮可打开右侧抽屉，显示原本的分析图表。
3.  所有账号（普通/超级）默认行为一致。
4.  图表功能在抽屉内正常工作。
