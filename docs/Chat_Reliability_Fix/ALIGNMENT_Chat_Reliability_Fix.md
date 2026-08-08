# 任务对齐文档：聊天可靠性修复与优化

## 1. 原始需求
用户反馈以下问题并提出改进建议：
1. 前端报错：`TypeError: Cannot read properties of undefined (reading 'top')`。
2. 偶发"获取AI恢复失败"，出现空对话框。
3. AI回复延迟，需刷新页面才能看到。
4. **核心优化需求**：
   - 用户发送消息落库即视为成功（Pending状态）。
   - 前端基于SSE实时接收AI回复。
   - 页面初始化时加载完整历史记录。
5. 确认改动是否推送到Docker。

## 2. 需求分析与理解
### 现有架构
- 前端：React + Ant Design
- 后端：FastAPI + Redis Pub/Sub + SSE
- 部署：Docker Compose (Frontend, Server, Worker)

### 关键改动点
1. **状态管理重构**：引入 `useChat` Hook 统一管理消息状态、SSE连接和历史记录加载。
2. **乐观UI更新**：发送消息时立即在前端显示，不等待后端处理完成。
3. **ID同步机制**：后端返回生成的 `user_message_id`，前端更新临时ID，确保状态一致。
4. **SSE增强**：连接建立后自动拉取历史记录，防止断连期间消息丢失；增加空消息过滤。
5. **部署流程**：更新 Docker 镜像以包含最新代码。

## 3. 验收标准
- [x] 无 `top` 属性相关报错。
- [x] 发送消息立即上屏，状态流转正常 (sending -> sent)。
- [x] AI 回复通过 SSE 实时逐字显示。
- [x] 刷新页面能完整加载历史记录。
- [x] Docker 容器包含最新代码并正常运行。

## 4. 疑问与澄清
- 无。
