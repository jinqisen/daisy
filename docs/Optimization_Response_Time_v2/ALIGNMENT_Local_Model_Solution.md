# ALIGNMENT_Local_Model_Solution

## 1. 现状与需求
*   **问题**: `summarize_topic` 调用远程 LLM (Huawei Cloud DeepSeek) 耗时过长 (69s+)。
*   **当前临时方案**: 禁用了总结功能，直接使用原始对话历史。
*   **用户需求**: "有没有什么本地部署的模型，可以解决summarize_topic问题"。
*   **测试结果**: 
    *   模型: `Qwen/Qwen2.5-0.5B-Instruct` (0.5B 参数量)
    *   环境: Docker 容器 (CPU)
    *   加载时间: ~3分钟 (首次下载 + 加载)
    *   推理时间: ~17秒 (生成简短总结)
    *   效果: 总结准确，中文支持良好。

## 2. 方案对比

| 方案 | 描述 | 耗时 | 优点 | 缺点 |
| :--- | :--- | :--- | :--- | :--- |
| **A. 保持禁用 (现状)** | 直接使用 Raw History | < 1s | 极速，无需额外资源 | 上下文窗口可能受限，缺乏深度分析 |
| **B. 本地 Qwen2.5-0.5B (推荐)** | 容器内加载小模型 | ~15-20s | 恢复总结能力，无需外网，成本低 | 增加内存开销，推理仍需 15s+ (不满足 <10s 极致体验) |
| **C. 本地 Qwen2.5-1.5B** | 稍大的模型 | ~30-40s | 效果更好 | 更慢，可能超过用户耐心阈值 |

## 3. 推荐方案 (B)
鉴于用户明确询问 "本地部署模型"，且 Qwen2.5-0.5B 在 CPU 上 ~17s 的表现是可以接受的（作为后台任务或并行任务），建议采用此方案。

### 3.1 实施细节
1.  **模型集成**:
    *   在 `app/services/llm.py` 或 `topic_agent.py` 中引入 `transformers`。
    *   增加 `LocalLLMService` 类，专门加载本地模型。
    *   **优化**: 在应用启动时 (`lifespan`) 预加载模型，避免每次请求都等待 3分钟。
2.  **调用逻辑**:
    *   `TopicAgent` 优先尝试使用 `LocalLLMService` 进行总结。
3.  **Docker 镜像**:
    *   需要确保 `model/` 目录挂载，避免重复下载。

## 4. 预期流程
1.  Server 启动 -> 预加载 `Qwen2.5-0.5B` -> 内存常驻 (~500MB)。
2.  `summarize_topic` 被调用 -> 使用本地模型推理 -> 耗时 ~15s。
3.  由于 `summarize_topic` 是独立的，如果它比 `analyze_communication_style` (30s) 快，则不会增加总响应时间（因为是并行的）。
    *   *Check*: `generate_response` 等待 `summarize_topic`。
    *   如果 `analyze_style` 需要 30s，而 `summarize_topic` (Local) 需要 17s，则**总耗时由最慢的决定** (30s)。
    *   **结论**: 引入本地模型**不会**恶化当前的 40s 响应时间，反而能恢复总结功能！

## 5. 执行步骤
1.  修改 `app/core/config.py`: 添加本地模型配置。
2.  修改 `app/main.py`: 增加本地模型预加载。
3.  修改 `app/services/topic_agent.py`: 实现本地推理逻辑。
