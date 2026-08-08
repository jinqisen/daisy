# TODO: 主动对话机制后续待办

## 1. 关键配置 (必做)
- [ ] **LLM API Key**: 确保 `.env` 文件中配置了有效的 LLM API Key (如 `OPENAI_API_KEY` 或其他)，否则主动对话无法生成内容。
- [ ] **Scheduler 启用**: 确保 `app/main.py` 中的 `lifespan` 正确启动了 Scheduler (目前代码已集成，需确认生产环境配置)。

## 2. 前端对接
- [ ] **SSE 处理**: 前端 `useChat.ts` 需要处理 `type: "proactive_message"` 的消息。
    - 目前逻辑可能会将其视为普通消息处理，建议验证样式是否符合预期。
- [ ] **心跳保活**: 确保前端与后端的 SSE 连接稳定，因为主动对话仅对在线用户生效。

## 3. 生产部署建议
- [ ] **Redis 持久化**: 生产环境 Redis 建议开启 AOF/RDB，防止重启丢失用户作息数据。
- [ ] **Worker 扩容**: 如果用户量大，需单独部署 Worker 容器集群。

## 4. 调试与监控
- [ ] **日志监控**: 关注 `ProactiveService` 的日志，特别是 `check_and_trigger` 的执行结果。
- [ ] **手动触发**: 可以通过 Swagger 或脚本手动调用 `check_and_trigger` 来测试特定用户的体验。
