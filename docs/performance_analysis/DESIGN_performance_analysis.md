# 性能分析报告设计

## 1. 报告结构
报告将分为以下几个部分：
1.  **概览 (Overview)**: 总耗时、请求 ID、发生时间。
2.  **详细阶段分析 (Stage Analysis)**:
    - 使用 Mermaid 甘特图展示各阶段并行/串行关系及耗时。
    - 表格列出每个节点的 Start Time, End Time, Duration。
3.  **瓶颈识别 (Bottlenecks)**:
    - 耗时最长的节点分析。
    - 异常日志（重试/错误）与耗时的关联。
4.  **原因推断 (Root Cause Analysis)**:
    - 网络问题 (Connection error)。
    - LLM 响应延迟 (LiteLLM)。
    - 并发执行效率。
5.  **优化建议 (Recommendations)**:
    - 针对网络稳定性的建议。
    - 针对 LLM 调用的建议（流式、缓存等）。

## 2. 数据流向
`Log Data` -> `Time Extraction` -> `Duration Calculation` -> `Bottleneck Identification` -> `Report Generation`

## 3. 核心指标
- **Total Latency**: 用户感知到的总延迟。
- **Node Latency**: 每个处理节点的延迟。
- **Wait Time**: 由于重试导致的等待时间。
