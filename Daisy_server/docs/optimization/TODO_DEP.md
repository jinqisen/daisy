# 待办事项清单 (DEP 优化后续)

## 已完成
- [x] 定义情感策略库 (`app/core/strategies.py`)
- [x] 升级 `agent_thoughts` 节点，支持策略选择 (`app/crew/service.py`)
- [x] 更新 CO-STAR Prompt 模板，注入策略意图 (`app/workflow/nodes/generation.py`)
- [x] 验证核心链路 (`tests/test_strategy_integration.py`)

## 待办事项
- [ ] **策略效果监控**: 在日志中专门过滤 `[Strategy]` 标签，观察线上对话的策略分布情况。
- [ ] **策略描述微调**: 根据实际效果，调整 `EmotionalStrategy` 中的文本描述，使 LLM 更容易理解每种策略的细微差别。
- [ ] **前端展示 (可选)**: 考虑在前端调试面板中显示当前 AI 选择的策略，增加系统的透明度。

## 缺失配置
- 无。目前使用的是硬编码的策略库，无需额外环境变量或数据库配置。
