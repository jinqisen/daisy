> **⚠️ 已归档 —— 前提不再成立**
> 本项目已从 server 部署转为单机桌面应用(零 Docker/零外部服务/免登录)。
> 本文档中的待办因架构变更而失效,无需执行。原因与全量清单见 [docs/ARCHIVED_TODOS.md](../../docs/ARCHIVED_TODOS.md)。

---
# 待办事项清单 (Huawei Migration)

## 配置检查
- [ ] **确认 Embedding 维度**: 华为云 BGE-M3 输出维度是否默认为 1024？如果不是，可能需要调整 `app/services/memory.py` 中的 `embedding_dims` 配置或重新索引向量数据库。
- [ ] **API 速率限制**: 检查华为云账号的配额，确保满足生产环境并发需求。

## 测试验证
- [ ] **全链路测试**: 运行一次完整的对话流程，确保话题总结、记忆检索、最终回复均正常工作。
- [ ] **CrewAI 验证**: 触发一次通过 CrewAI 的深度思考/人格互动，确保其仍然正常使用 SiliconFlow (检查日志中的模型名称或 Endpoint)。

## 部署
- [ ] **Docker 环境变量**: 如果使用 Docker 部署，请确保在 `docker-compose.yml` 或运行命令中注入新增的 `HUAWEI_` 环境变量。
