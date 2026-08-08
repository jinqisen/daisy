# CONSENSUS_docker_gpu_support

## 1. 最终共识

### 需求描述
用户希望在 Windows 环境下，通过 Docker 运行 `Daisy_server` 时能够调用本地 NVIDIA GPU。

### 验收标准
1.  `build_local_image.ps1` 脚本成功执行，容器正常启动。
2.  容器内部能够识别 GPU (例如通过 `nvidia-smi` 或 PyTorch 检查)。

## 2. 技术方案

### 核心变更
- 修改 `e:\Daisy\Daisy_Demo\Daisy_server\scripts\build_local_image.ps1`。
- 在 `docker run` 命令中添加 `--gpus all` 参数。

### 环境依赖
- **宿主机**: Windows 10/11, NVIDIA Driver, Docker Desktop (WSL 2 Backend enabled).
- **容器**: 基于 `python:3.10-slim`，依赖 Docker 的 GPU 注入机制。

## 3. 风险与限制
- 如果宿主机未配置 WSL 2 GPU 支持，该参数可能会导致容器启动失败。
- 基础镜像 `python:3.10-slim` 可能缺少某些特定的 CUDA 库（如 `nvcc`），但运行 PyTorch 推理通常足够。

## 4. 任务计划
- [ ] 修改构建脚本。
- [ ] 验证容器启动。
