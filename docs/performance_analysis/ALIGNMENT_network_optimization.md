# 优化 Docker 网络架构任务对齐文档

## 1. 需求描述
将当前基于 `host.docker.internal` 的容器通信方式，优化为基于 Docker Bridge 网络的直接通信方式。

## 2. 变更范围
### 2.1 网络创建
- 创建一个名为 `daisy_local_network` 的 Docker Bridge 网络。

### 2.2 `daisy_server/scripts/build_local_deps.ps1`
- 检查并创建 `daisy_local_network`。
- Redis 容器 (`daisy_redis_local`) 启动时加入该网络。
- Qdrant 容器 (`daisy_qdrant_local`) 启动时加入该网络。

### 2.3 `daisy_server/scripts/build_local_image.ps1`
- Server 容器 (`daisy_server_local_container`) 启动时加入该网络。
- 覆盖环境变量：
    - `REDIS_HOST` -> `daisy_redis_local`
    - `REDIS_PORT` -> `6379` (容器内部端口)
    - `QDRANT_HOST` -> `daisy_qdrant_local`
    - `QDRANT_PORT` -> `6333` (容器内部端口)

## 3. 预期效果
- 容器间通信不再依赖宿主机网络栈，避免 IPv6 解析延迟。
- 保持对外端口映射不变，方便外部调试。
- 提升连接稳定性。
