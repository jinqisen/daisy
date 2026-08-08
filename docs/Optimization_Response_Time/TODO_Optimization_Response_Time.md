# TODO_Optimization_Response_Time

## 待办事项
1.  **Prompt 耗时优化 (建议)**:
    *   日志显示 `PromptEngineer` 耗时约 28秒。这是一个巨大的优化空间。
    *   建议: 审查 Prompt 长度，考虑简化 Prompt，或尝试更快的 LLM 模型 (如 DeepSeek-V3 Turbo 等)。
2.  **监控完善**:
    *   当前通过 Docker 日志分析耗时较为繁琐。
    *   建议: 引入 Prometheus/Grafana 或更详细的结构化日志 (JSON logs)，以便自动监控各节点的 P95/P99 耗时。
