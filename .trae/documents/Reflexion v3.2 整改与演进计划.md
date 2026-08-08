# Reflexion v3.2 整改与演进计划

本计划旨在落实 Reflexion 模块的技术修复与架构升级，重点解决评分准确性、闭环能力及共性/个性学习机制的缺失。

## Phase 1: 文档固化与契约对齐 (Documentation & Alignment)
**目标**: 确立 v3.2 为单一技术真理来源，明确指标定义。
1.  **落库评审报告**: 创建 `docs/Reflexion/TECHNICAL_REVIEW_Reflexion_v3.md`，记录现状差异与风险。
2.  **发布新设计规范**: 创建 `docs/Reflexion/DESIGN_Reflexion_Learning_v3.2.md`，详细定义 Q_I/E_U/D_R 新公式及共性/个性学习架构。
3.  **标记旧文档**: 在原 `AI 伴侣用户满意度评估...md` 头部添加 Deprecated 声明，指向新文档。

## Phase 2: 核心指标与数据流修正 (Core Metrics Fix)
**目标**: 修复评分逻辑，使 S 分数具备数学意义与可信度。
1.  **修正数据契约**:
    *   重构 `ReflexionService.process_turn` 签名，明确 `agent_emotion` (AI当前), `target_emotion` (策略目标), `user_emotion` (用户当前) 的传递。
    *   在 `generation.py` 中正确提取并传递这些参数（特别是从 Strategy 获取 target_emotion）。
2.  **升级 MetricsService**:
    *   **M_emo**: 实现向量距离算法 ($1 - ||v_{actual} - v_{target}|| / \sqrt{2}$)。
    *   **M_hum**: 实现 TTR + 句长标准差算法。
    *   **D_R**: 引入 `RelationshipDepth` 计算逻辑（基于 Session 频次 + Memory 密度）。
    *   **S**: 更新综合分公式为 `0.5*Q_I + 0.3*E_U + 0.2*D_R`。

## Phase 3: 持久化与采样机制 (Persistence & Sampling)
**目标**: 建立数据闭环基础，降低系统负载。
1.  **反思日志落库**:
    *   在 `ReflexionService` 中调用 `ReflexionLogDB` 写入逻辑，保存每轮的评分详情与 Metadata。
2.  **实现 Trigger & Sampling**:
    *   在 `AsyncReflexionSystem` 中增加过滤器：仅在“长对话、情绪波动大、意图关键”或“随机 10%”时触发重计算，避免每轮空耗。

## Phase 4: 闭环与学习路径 (Closing the Loop)
**目标**: 让 Reflexion 真正影响生成（RAG + Patching）。
1.  **RAG 检索注入**:
    *   在 `generation.py` 流程中增加 `reflexion_storage.retrieve_exemplars` 调用。
    *   实现“共性 (Global) + 个性 (Personal)”混合检索策略。
2.  **Patching 策略优化**:
    *   确保 Patch 生成时正确标记 Scope (GLOBAL/PERSONAL)。

## Phase 5: 架构反思与验收 (Reflection)
1.  执行静态检查与测试。
2.  编写架构反思报告，总结改动后的系统特性与遗留挑战。
