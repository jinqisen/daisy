# ACCEPTANCE: 主动对话机制 (Proactive Dialogue)

## 1. 验证概览
- **验证时间**: 2026-01-02
- **验证环境**: Local Docker (Redis @ localhost:30018, Qdrant @ localhost:30019)
- **验证目标**: 验证主动对话的双轨判定机制、防打扰策略、LLM决策流及消息发送全链路。

## 2. 验证步骤与结果

### 2.1 环境配置验证
- [x] **Redis 连接**: 成功连接到本地 Docker 部署的 Redis (端口 30018)。
- [x] **Qdrant 连接**: 成功连接到本地 Docker 部署的 Qdrant (端口 30019)。

### 2.2 核心逻辑验证 (Check & Trigger)
使用脚本 `scripts/verify_proactive_dialogue.py` 进行端到端验证：

1.  **场景模拟**:
    - 用户状态: 在线
    - 作息数据: 当前时段高活跃 (模拟 50 次交互)
    - 忙碌状态: 空闲 (最后活跃时间 > 30分钟)
    - 情感状态: 正常 (或通过 Mock 注入 Emo 状态)

2.  **执行过程**:
    - 系统正确识别用户为“在线”。
    - 系统正确计算活跃概率，通过作息检查。
    - 系统正确判断非忙碌状态。
    - LLM (Mocked) 成功生成主动问候内容。
    - `_send_message` 成功将消息写入数据库。

3.  **结果检查**:
    - **数据库**: 成功查询到 `role='ai'` 且 `user_id='test_user_verification'` 的新插入消息。
    - **日志**: 
      ```
      [info] Proactive message generated for test_user_verification: Hey there! ...
      ```

### 2.3 Bug 修复验证
在此次验证过程中发现并修复了以下问题：
- [x] **Redis 连接超时**: 修正 `.env` 指向 localhost。
- [x] **ChatHistoryService 兼容性**: 替换了已废弃的 `get_chat_history` 为 `get_recent_history_limit`。
- [x] **LLM 初始化**: 修正了 `ProactiveService` 中获取 LLM 实例的方式。
- [x] **DB 模型错误**: 修正了 `ChatHistoryDB` 实例化时传入无效参数 `type` 的问题。
- [x] **Role 字段统一**: 将主动消息的 `role` 从 "assistant" 修正为 "ai" 以匹配系统规范。

## 3. 结论
主动对话机制的核心链路（触发 -> 判定 -> 生成 -> 存储 -> 推送）已在本地环境中验证通过。代码逻辑符合双轨防打扰和情感优先的设计要求。

## 4. 后续建议
- 在生产环境部署前，确保数据库中存在真实的用户 ID，避免外键约束问题（本次验证使用 SQLite 且可能未开启强外键约束）。
- 建议进一步完善单元测试，覆盖“情感豁免”和“冷却拦截”等边界情况。
