# 双层 Session 管理架构设计方案 (v1.0)

## 1. 概述 (Overview)

当前系统使用单一的 `session_id` 混合了“技术连接”和“业务对话”两个概念，导致以下问题：
1.  **上下文碎片化**: WebSocket 断开或页面刷新会导致 Session ID 变更，进而丢失短期记忆（Short-term Memory）。
2.  **意图不连贯**: AI 无法区分“网络重连”与“新话题开始”，容易在用户只是稍作停顿后就重置对话状态。
3.  **生命周期混淆**: 鉴权 Token 的有效期与对话上下文的有效期耦合。

本方案提出 **双层 Session 架构**，明确区分技术层与业务层，以实现更健壮的会话管理。

---

## 2. 核心概念定义

### 2.1 技术会话 (Connection Session)
*   **职责**: 维护客户端与服务端的实时通信链路。
*   **生命周期**: 短暂。随网络状态、页面刷新、App 前后台切换而变化。
*   **标识**: `connection_id` (WebSocket ID) 或 `client_token`。
*   **关键数据**: 
    *   用户在线状态 (Online/Offline)
    *   消息推送通道 (SSE/WebSocket)
    *   鉴权信息 (User Identity)

### 2.2 业务会话 (Conversation Session)
*   **职责**: 维护对话的逻辑连续性、上下文窗口和短期记忆。
*   **生命周期**: 较长。跨越多个技术会话，由**话题连续性**或**时间窗口**决定边界。
*   **标识**: `conversation_id` (UUID)。
*   **关键数据**:
    *   短期记忆窗口 (Context Window)
    *   话题摘要 (Topic Summary)
    *   情感累积状态 (Emotional State)

---

## 3. 架构设计 (Architecture)

### 3.1 数据模型变更

#### Redis 存储结构
引入 `SessionService` 负责管理以下 Redis Key：

1.  **活跃业务会话映射**:
    *   Key: `session:active_conversation:{user_id}`
    *   Value: `conversation_id`
    *   TTL: 4小时 (每次交互自动续期)
    *   **作用**: 快速查找用户当前是否处于一个未结束的对话流中。

2.  **业务会话元数据**:
    *   Key: `session:conversation:{conversation_id}:meta`
    *   Value: JSON
        ```json
        {
          "start_time": "2024-01-12T10:00:00",
          "last_interaction": "2024-01-12T10:05:00",
          "topic_summary": "讨论电视剧《大商人》...",
          "status": "active" // active, archived
        }
        ```
    *   TTL: 24小时 (归档后保留一段时间以便查询)

#### 数据库模型 (SQLAlchemy)
保持 `ChatHistoryDB` 表结构不变，但明确字段语义：
*   `session_id` 字段存储 **业务会话 ID (`conversation_id`)**。
*   新增 `ConversationDB` 表 (可选，用于更精细的分析)：
    ```python
    class ConversationDB(Base):
        __tablename__ = "conversations"
        id = Column(String, primary_key=True)
        user_id = Column(Integer, ForeignKey("users.id"))
        start_time = Column(DateTime)
        end_time = Column(DateTime, nullable=True)
        summary = Column(Text) # 最终话题总结
    ```

### 3.2 业务流程 (Workflow)

#### A. 用户发送消息 (User Sends Message)

1.  **鉴权与连接**: API Gateway 验证 Token，建立技术连接。
2.  **获取业务会话**:
    *   调用 `SessionService.get_active_conversation(user_id)`。
    *   **Case 1: 存在活跃会话**:
        *   返回 `conversation_id`。
        *   检查是否发生**话题漂移 (Topic Shift)** (高级特性，可选)。
    *   **Case 2: 无活跃会话 (超时或新用户)**:
        *   创建新的 `conversation_id`。
        *   记录 `Start Event` 到数据库。
3.  **处理消息**:
    *   使用 `conversation_id` 标记消息记录 (`ChatHistoryDB`).
    *   LangGraph 工作流使用 `conversation_id` 检索上下文。
4.  **续期**:
    *   更新 `session:active_conversation:{user_id}` 的 TTL 为 4小时。

#### B. 会话结束 (Session Termination)

1.  **自动结束 (TTL)**:
    *   用户停止交互超过 4 小时，Redis Key 过期。
    *   下次用户回来时，Case 2 触发，新会话开始。
2.  **主动结束**:
    *   用户输入“再见”、“晚安”。
    *   系统调用 `SessionService.end_conversation(conversation_id)`。
    *   触发 **后台归档任务**:
        *   生成最终会话摘要。
        *   写入 Qdrant 长期记忆。
        *   清除 Redis 活跃状态。

---

## 4. 迁移策略 (Migration Strategy)

为了“不急着修改代码”，我们采取渐进式迁移：

### 阶段 1: 逻辑模拟 (当前状态)
*   **不引入新表**。
*   **逻辑调整**: 修改 `server.py` 和 `chat.py` 中的 `session_id` 生成逻辑。
    *   将原本的 `30分钟` 判定窗口延长至 `4小时`。
    *   **实质**: 用“长 Session ID”模拟“业务会话 ID”。
    *   **现状**: 已完成。

### 阶段 2: 引入 SessionService (计划中)
*   创建一个独立的 `app/services/session_service.py`。
*   将散落在 `server.py` 中的 Session 判断逻辑收敛到该 Service 中。
*   引入 Redis 管理 `active_conversation`。

### 阶段 3: 完善元数据
*   创建 `ConversationDB` 表。
*   在会话结束时触发“记忆固化”流程 (Memory Consolidation)。

---

## 5. 接口定义 (Interface Definition)

```python
# app/services/session_service.py

class SessionService:
    async def get_active_conversation(self, user_id: int) -> str:
        """
        获取当前用户的活跃业务会话 ID。
        如果 Redis 中不存在，则检查 DB 中最近一条消息的时间。
        如果都过期，则生成新 ID。
        """
        pass

    async def touch_conversation(self, conversation_id: str, ttl: int = 14400):
        """
        续期会话。
        """
        pass

    async def end_conversation(self, conversation_id: str):
        """
        显式结束会话，触发归档和记忆提取。
        """
        pass
```
