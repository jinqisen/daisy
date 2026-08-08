# 共识文档：Task 分批处理与历史记录逻辑 (CONSENSUS)

## 1. 核心场景对齐
用户描述的场景完全符合系统的设计预期，我们达成以下共识：

### 1.1 场景描述
1.  **阶段一**: 用户发送 `A` -> Task 锁定并处理 -> 生成 `TaskA` 回复。
2.  **阶段二**: 在 Task 处理 A 的期间，用户发送 `B` 和 `C` -> 进入队列 (Pending)。
3.  **阶段三**: Task A 完成后，Worker 发现队列中有 `B` 和 `C` -> 合并处理 -> 生成 `TaskBC` 回复。

### 1.2 数据结构结论
在此场景下，系统产生的历史记录为 **2 个 Pair**：
1.  **Pair 1**: `[User: A, AI: TaskA]`
2.  **Pair 2**: `[User: B, User: C, AI: TaskBC]`

这符合用户 "A/taskA，BC/taskBC是2pair数据" 的预期。

## 2. 逻辑审视与验证

### 2.1 Task 消费逻辑 (`worker.py`)
*   **代码行为**: 采用 `while True` 循环 + `filter(status='pending')`。
*   **分析**:
    *   Worker 处理完 A 后，不释放锁，立即查询所有 Pending 消息。
    *   它会一次性捞起 `B` 和 `C`。
    *   执行 `merged_content = "\n".join([B, C])`。
    *   将合并后的内容送入 LLM。
*   **结论**: **无需修改**。逻辑已支持 "把BC当做一条消息进行处理"。

### 2.2 历史记录获取逻辑 (`topic_agent.py` + `chat_history.py`)
*   **关键点**: 在处理 `BC` 时，LLM 需要看到 `Pair 1 (A/TaskA)` 作为历史，但**不能**看到 `B` 和 `C` (因为它们是当前输入)。
*   **此前修正**: 我们刚刚增加了 `exclude_statuses=["pending", "processing"]` 参数。
*   **执行流**:
    1.  Task A 完成，状态变为 `completed`。
    2.  Task BC 开始，B 和 C 状态变为 `processing`。
    3.  `TopicAgent` 获取历史 -> 排除 `processing` (即排除 B 和 C)。
    4.  **结果**: 历史记录仅包含 `[A, TaskA]` (以及更早的)。
*   **结论**: **无需修改**。此前的去重修正已完美覆盖此逻辑。

### 2.3 Pair 分组逻辑 (`utils.py`)
*   **代码行为**: `group_chat_history_by_pairs`。
*   **分析**:
    *   算法：`[B, C, TaskBC]`。
    *   遇到 B: 新组 `[B]`。
    *   遇到 C: 当前组无 AI -> 追加 -> `[B, C]`。
    *   遇到 TaskBC: 追加 -> `[B, C, TaskBC]`。
*   **结论**: **无需修改**。算法天然支持 "多 User 对 单 AI" 的分组，会被正确统计为 1 个 Pair。

## 3. 最终结论
经过对 `worker.py` (消费)、`topic_agent.py` (上下文) 和 `utils.py` (分组) 的全面审视：

1.  **逻辑完全对齐**: 当前代码实现与您描述的业务逻辑完全一致。
2.  **无需额外修改**: 基于上一轮进行的“去重参数”优化，系统已能正确处理该场景，不会出现上下文重复或丢失。
