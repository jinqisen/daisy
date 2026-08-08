# 设计文档：右侧分析面板抽屉化

## 1. 架构调整
### 1.1 组件提取
创建一个新组件 `src/components/AnalysisDashboard.tsx`，将 `App.tsx` 中 Tab 1 右侧 `Col` 的内容移入。

**Props 定义**:
```typescript
interface AnalysisDashboardProps {
  visualState: {
    emotions: any[];
    personality: string;
    weights: any;
    engagementHistory: any[];
    emotionHistory: any[];
    personalityHistory: any[];
  };
  logs: any[];
  latestUserMessageId: number | null;
  isSuperUser: boolean;
}
```

### 1.2 App.tsx 布局变更
- 在 `Header` 中添加一个 `Button`，图标为 `BarChartOutlined` 或 `MenuUnfoldOutlined`，点击切换 `drawerVisible`。
- Tab 1 的 `children` 布局改为：
  - `ChatInterface` 占据 `width: 100%`。
  - 添加 `<Drawer>` 组件。
    - `placement="right"`
    - `width="70%"` (或响应式宽度)
    - `onClose={() => setDrawerVisible(false)}`
    - `open={drawerVisible}`
    - `mask={false}` (可选，如果希望可以点击背景关闭则设为 true，如果希望并在则设为 false。根据“抽屉”通常行为，默认 mask=true)
    - `body` 内容为 `<AnalysisDashboard />`。

## 2. 数据流
- `App.tsx` 依然持有所有状态。
- 状态通过 Props 传递给 `AnalysisDashboard`。

## 3. 详细步骤
1.  新建 `src/components/AnalysisDashboard.tsx`。
2.  修改 `src/App.tsx`，引入 `Drawer` 和新组件，移除旧的 Layout 代码。
3.  添加 `drawerVisible` 状态，默认 `false`。
4.  在 `Header` 添加触发按钮。

## 4. 依赖
- `@ant-design/icons`: 需要引入新的图标。
- `antd`: Drawer 组件。
