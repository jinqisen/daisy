# Reflexion v3.2：架构与学习策略

**版本**: 3.2
**状态**: 已批准
**替代**: `AI 伴侣用户满意度评估：建模与算法方案.md`

---

## 1. 概览

Reflexion v3.2 是 AI 伴侣的自我进化机制。它通过评估交互来生成综合满意度评分 ($S$)，并利用该评分驱动两条独特的学习路径：**共性学习 (Global Learning)**（为所有人改进系统）和 **个性偏好学习 (Personal Learning)**（适应个体用户）。

## 2. 综合满意度评分 ($S$)

核心指标 $S \in [0, 1]$ 是三个层面的加权和：

$$ S = w_I \cdot Q_I + w_E \cdot E_U + w_R \cdot D_R $$

**推荐权重**: $w_I=0.5, w_E=0.3, w_R=0.2$.

### 2.1 交互质量 ($Q_I$) - "我回答得好吗？"
在生成后立即（或异步）评估。

*   **$M_{coh}$ (连贯性)**: 回复与上下文的语义相似度 (SBERT)。
*   **$M_{hum}$ (拟人度)**: 统计自然度。
    *   $$ M_{hum} = 0.4 \cdot \text{Norm}(TTR) + 0.6 \cdot \text{Norm}(\sigma_{len}) $$
*   **$M_{emo}$ (情感理性)**: 与策略的对齐度。
    *   $$ M_{emo} = 1 - \frac{1}{\sqrt{2}} \|\mathbf{v}_{actual} - \mathbf{v}_{target}\|_2 $$
    *   目标来自于策略模块 (例如，“共情支持”)。

### 2.2 用户参与度 ($E_U$) - "用户喜欢吗？"
在*下一*用户轮次 ($u_{t+1}$) 后评估。

*   **$M_{cont}$ (话题延续性)**: $r_t$ 与 $u_{t+1}$ 的相似度。
*   **$M_{rtl}$ (RTL 比率)**: 回复长度 / 回复时间比率。
*   **$M_{sent}$ (情感提升)**: $\text{Valence}(u_{t+1}) - \text{Valence}(u_t)$。

### 2.3 关系深度 ($D_R$) - "我们亲密吗？"
基于长期统计数据评估。

*   **$M_{freq}$**: 会话频率和留存率 (7天窗口)。
*   **$M_{mem}$ (记忆密度)**: 长期记忆 (Mem0) 更新的频率。
    *   用“有意义的信息交换”取代“任务完成度”。

---

## 3. 双路径学习策略

Reflexion 利用 $S$ 触发存储 (RAG) 和修正 (Patching) 在两个作用域中进行。

### 3.1 共性学习 (Scope: GLOBAL)
*   **目标**: 提升通用性能，修复普遍 Bug，强制安全。
*   **数据源**:
    *   **高 $S$**: 在*多名用户*间成功的模式。
    *   **低 $S$**: 在*多名用户*间发生的错误。
*   **机制**:
    *   **共性范例 (Global Exemplars)**: 存储时标记 `user_id="*"` 或 `scope="GLOBAL"`。在相似上下文中为所有用户检索。
    *   **共性补丁 (Global Patches)**: 为所有人注入系统提示词的规则（例如，“不要使用翻译腔”）。

### 3.2 个性偏好学习 (Scope: PERSONAL)
*   **目标**: 适应特定用户的语气、边界和话题。
*   **数据源**:
    *   **高 $S$**: 用户特定的正向强化（例如，“用户 A 喜欢简短回答”）。
    *   **低 $S$**: 用户特定的负面反馈。
*   **机制**:
    *   **个性范例 (Personal Exemplars)**: 存储时标记 `user_id="{uid}"`。仅为该用户检索。
    *   **个性补丁 (Personal Patches)**: 仅为该用户注入的规则（例如，“用户 A 讨厌表情符号”）。
    *   **长期记忆**: 存储在 Mem0 中的事实和偏好。

---

## 4. 架构与数据流

### 4.1 滞后结算 ("回合制" 流程)

1.  **轮次 $T$ (生成)**:
    *   AI 生成 $r_T$。
    *   计算 $Q_I(T)$。
    *   存储 `Pending({u_T, r_T, Q_I})` 到 Redis。
2.  **轮次 $T+1$ (用户输入)**:
    *   用户发送 $u_{T+1}$。
    *   **Reflexion Worker** 唤醒:
        1.  检索 `Pending(T)`。
        2.  利用 $u_{T+1}$ 计算 $E_U(T)$。
        3.  获取 $D_R$ 统计。
        4.  计算 $S(T)$。
        5.  **触发进化**:
            *   如果 $S > 0.85$: 存储 RAG 范例 (应用 Global/Personal 逻辑)。
            *   如果 $S < 0.40$: 生成补丁 (LLM 决定 Scope)。
        6.  记录到 `ReflexionLogDB`。

### 4.2 检索注入 (循环)

在生成 $r_{T+1}$ 期间:
1.  **检索补丁**: `get_active_patches(user_id)` -> 返回 Global + Personal 补丁。
2.  **检索范例**: `retrieve_exemplars(context, user_id)` -> 返回相关的高 $S$ 对话。
3.  **注入**: 添加到系统提示词 (System Prompt)。

---

## 5. 实施路线图

1.  **指标更新**: 实现向量 $M_{emo}$，统计 $M_{hum}$，和 $D_R$。
2.  **持久化**: 启用 DB 记录。
3.  **RAG 注入**: 连接存储与生成。
4.  **学习逻辑**: 细化 Global 与 Personal 的判定阈值。

---

## 附录 A: 算法详情与参数 (Algorithm Details)

以下是各指标的具体计算公式与参数设定，参考自原 `ALGORITHM_Reflexion_Metrics_v3.md`。

### A.1 上下文连贯性 ($M_{coh}$)
*   **公式**:
    $$ M_{coh} = \text{Sigmoid}\left( \gamma \cdot \left( \frac{1}{K} \sum_{i=1}^{K} \cos(\mathbf{e}_{r_t}, \mathbf{e}_{u_{t-i}}) - \theta_{coh} \right) \right) $$
*   **参数**:
    *   $K=3$: 历史窗口。
    *   $\theta_{coh}=0.3$: 相似度基准。
    *   $\gamma=10$: Sigmoid 陡度。

### A.2 回复投入度 ($M_{rtl}$)
*   **公式**:
    $$ M_{rtl} = \text{Tanh}\left( \frac{\ln(L_{u_{t+1}} + 1)}{\ln(\Delta T + e)} \cdot \lambda \right) $$
*   **参数**:
    *   $L$: 用户回复字数。
    *   $\Delta T$: 用户思考耗时 (秒)。
    *   $\lambda=2.0$: 调节系数。

### A.3 动态权重路由表
根据 NLU 识别的意图动态调整权重：

| 意图类型 | 权重调整策略 | 核心逻辑 |
| :--- | :--- | :--- |
| **Emotional Support** | $w(M_{emo}) \uparrow, w(M_{sent}) \uparrow$ | 优先关注情绪安抚 ($M_{emo}$) 和用户情绪改善 ($M_{sent}$)。 |
| **Information Seeking** | $w(M_{coh}) \uparrow, w(M_{task}) \uparrow$ | 优先关注答案准确性 ($M_{coh}$) 和问题解决 ($M_{task}$)。 |
| **Casual Chat** | $w(M_{hum}) \uparrow, w(M_{cont}) \uparrow$ | 优先关注聊天趣味性 ($M_{hum}$) 和话题延续 ($M_{cont}$)。 |

---

## 附录 B: 实现规范 (Implementation Specs)

以下是数据存储与 Prompt 结构的具体规范，参考自原 `DESIGN_Dual_Layer_Reflexion.md`。

### B.1 补丁存储 Schema (`reflexion_patches.jsonl`)

```json
{
  "user_id": "123",           // Required for PERSONAL, Optional/Ignored for GLOBAL
  "patch": "Do not use emojis.",
  "scope": "PERSONAL",        // "GLOBAL" | "PERSONAL"
  "score": 0.2,
  "reasoning": "User expressed annoyance at playful tone.",
  "status": "active",
  "created_at": "2023-10-27T10:00:00"
}
```

### B.2 系统提示词注入结构

在生成回复时，System Prompt 将动态插入以下部分：

```markdown
... [Base System Prompt] ...

### 🛡️ Global Protocols
(Applies to everyone)
- [Global Patch 1]
- [Global Patch 2]

### 👤 Personal Adaptations
(Customized for User {user_id})
- [Personal Patch 1]
- [Personal Patch 2]
```
