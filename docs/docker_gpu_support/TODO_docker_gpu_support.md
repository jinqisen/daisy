> **⚠️ 已归档 —— 前提不再成立**
> 本项目已从 server 部署转为单机桌面应用(零 Docker/零外部服务/免登录)。
> 本文档中的待办因架构变更而失效,无需执行。原因与全量清单见 [docs/ARCHIVED_TODOS.md](../../docs/ARCHIVED_TODOS.md)。

---
# TODO_docker_gpu_support

## 待办事项
- [ ] **用户验证**: 请用户运行 `build_local_image.ps1` 并使用提供的命令验证 GPU。
- [ ] **性能测试**: 如果用于 LLM 推理，建议对比开启 GPU 前后的推理速度。

## 配置建议
- 如果遇到显存不足 (OOM)，可以考虑在 `docker run` 中限制可见 GPU (例如 `--gpus device=0`)，或者调整模型量化设置。
