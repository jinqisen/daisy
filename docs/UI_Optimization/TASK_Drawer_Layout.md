# 任务清单：右侧分析面板抽屉化

## Task 1: 创建 AnalysisDashboard 组件
- **文件**: `src/components/AnalysisDashboard.tsx`
- **内容**: 将 `App.tsx` 中原本渲染右侧分析面板的代码迁移至此。
- **输入**: `visualState`, `logs`, `latestUserMessageId`, `isSuperUser`。
- **依赖**: 引用相关的图表组件 (`StateVisualizer`, `CommunicationAnalysisCard`, `EmotionTrendChart` 等)。

## Task 2: 修改 App.tsx 布局
- **文件**: `src/App.tsx`
- **步骤**:
    1.  引入 `AnalysisDashboard` 和 `Drawer`。
    2.  添加 `drawerVisible` 状态 (useState)。
    3.  修改 Tab 1 的渲染逻辑，移除 Row/Col 分栏，让 ChatInterface 独占。
    4.  添加 `Drawer` 组件包裹 `AnalysisDashboard`。
    5.  在 `Header` 添加控制按钮。

## Task 3: 验证
- **检查**:
    - 默认加载时是否只有聊天界面。
    - 点击按钮是否能滑出抽屉。
    - 抽屉内的图表是否正常显示。
    - 切换账号（SuperUser/普通）是否行为一致。
