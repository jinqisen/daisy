# ALIGNMENT_docker_gpu_support

## 1. 项目上下文分析

### 现有项目结构
- **Daisy_server**: 后端服务，目前运行在 Docker 容器中。
- **构建脚本**: `e:\Daisy\Daisy_Demo\Daisy_server\scripts\build_local_image.ps1`
- **基础镜像**: `python:3.10-slim` (在 `Dockerfile.base` 中定义)

### 需求理解
- **原始需求**: "我需要在docker中能够调用本地gpu，需要做什么"
- **目标**: 使 `Daisy_server` 容器能够利用宿主机的 NVIDIA GPU 进行计算（如 LLM 推理、嵌入生成等）。
- **环境**: Windows + Docker Desktop (WSL 2 backend)。

## 2. 关键决策点与疑问

### 2.1 基础镜像选择
- **选项 A**: 保持 `python:3.10-slim`。
  - **优点**: 镜像体积小，无需更改 Dockerfile 结构。
  - **条件**: 依赖 Docker Desktop 的 WSL 2 GPU 穿透功能。需要在 `requirements.txt` 中确保安装了 CUDA 版本的 PyTorch。
- **选项 B**: 切换到 `nvidia/cuda` 基础镜像。
  - **优点**: 包含完整的 CUDA Toolkit，环境更标准。
  - **缺点**: 镜像体积大，需要重写 Dockerfile。
- **决策**: 优先尝试 **选项 A**。如果应用仅依赖 PyTorch 等高层库，它们通常自带所需的 CUDA 运行时库，配合 Docker Desktop 的驱动注入即可工作。

### 2.2 PyTorch 依赖
- 当前 `requirements.txt` 是否指定了 CPU 版本？需要检查。
- 如果是默认安装，Linux 下 pip 通常安装的是带 CUDA 的版本，但需要确认版本兼容性。

### 2.3 运行时参数
- 必须在 `docker run` 中添加 `--gpus all`。

## 3. 行动计划

### 3.1 检查
- 检查 `Daisy_server/requirements.txt` 中的依赖定义。

### 3.2 修改
- 修改 `Daisy_server/scripts/build_local_image.ps1`: 添加 `--gpus all` 参数。
- (如果需要) 修改 `Daisy_server/requirements.txt`: 指定 GPU 版本的 PyTorch 源。

### 3.3 验证
- 创建一个简单的验证脚本或使用现有代码检查 `torch.cuda.is_available()`。
