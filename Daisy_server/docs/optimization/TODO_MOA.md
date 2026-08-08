# 待办事项清单 (MOA 优化后续)

## 已完成
- [x] Phase 1: 显式多目标思维链 (Explicit Multi-Objective CoT)
  - [x] 定义评分标准 `app/core/rubrics.py`
  - [x] 升级 `crew/service.py` 注入 Rubric Check
  - [x] 验证集成测试

## 待办事项 (Phase 2 - 动态优先级)
- [ ] **配置扩展**: 在 `CommonSettings` 中增加 `priority_mode` 字段 (Style-First / Fact-First)。
- [ ] **Prompt 适配**: 根据 `priority_mode` 动态调整 `[Rubric_Check]` 的指令权重（例如：如果 Fact-First，则强调准确性检查）。

## 待办事项 (Phase 3 - Rubric RAG)
- [ ] **数据收集**: 收集 50+ 条高质量对话示例。
- [ ] **数据标注**: 为示例打上 `style_score`, `empathy_score` 等标签。
- [ ] **RAG 实现**: 实现基于当前对话状态检索高分示例的逻辑。

## 待办事项 (监控与调优)
- [ ] **日志分析**: 观察线上日志中的 `[Rubric_Check]` 输出，看 Agent 是否真的在进行有效的自我反思，还是在敷衍（Hallucination）。
