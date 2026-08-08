# 待办事项清单 (Optimization & Refactoring)

## 1. 监控与日志
- [ ] **添加缓存命中日志**: 在 `generation.py` 的各节点中添加 `logger.debug("Using cached settings/profiles from state")`，以便在生产环境中验证优化效果。

## 2. 进一步性能优化
- [ ] **Redis 二级缓存**: 将 `RoleProfile` 和 `CommonSettings` 缓存到 Redis 中，设置合理的过期时间（如 5 分钟），进一步减少数据库压力。
- [ ] **节点并行化**: 分析 `analyze_style` 和 `ensure_portrait` 等节点是否存在依赖关系，尝试将其并行执行以降低总延迟。

## 3. 架构改进
- [ ] **流式响应改造 (Streaming)**: 将 `generate_response` 改造为支持 Server-Sent Events (SSE)，提升用户感知的响应速度。
- [ ] **配置中心**: 将分散在各处的默认配置（如默认 Prompt 模板）统一管理。
