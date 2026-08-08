# DESIGN_docker_gpu_support

## 1. 架构设计

### 部署架构
- **Host**: Windows (WSL 2) + NVIDIA Driver
- **Docker Daemon**: Managed by Docker Desktop, supports NVIDIA Container Toolkit.
- **Container**: `daisy_server_local_container`
  - **Runtime**: `--gpus all` flag enables GPU access.
  - **App**: Python application utilizing PyTorch/Transformers.

### 数据流
无数据流变更。

## 2. 接口设计
无接口变更。仅修改启动参数。
