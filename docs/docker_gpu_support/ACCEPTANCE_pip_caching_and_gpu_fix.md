# ACCEPTANCE_pip_caching_and_gpu_fix

## 1. 变更摘要

### 1.1 Docker 构建优化 (PIP 缓存)
- **文件**: `Daisy_server/Dockerfile.base`
- **变更**:
    - 启用了 Docker BuildKit 语法 `# syntax=docker/dockerfile:1`。
    - 在 `apt-get` 和 `pip install` 指令中添加了 `--mount=type=cache`。
    - **效果**: 依赖包下载后会缓存到 Docker 宿主机的卷中，后续构建（即使修改了 `requirements.txt`）可复用未变更的包，显著加快构建速度。

### 1.2 GTX 1060 兼容性修复
- **文件**: `Daisy_server/Dockerfile.base`
- **变更**:
    - 强制安装 `torch==2.1.2+cu118` (CUDA 11.8)。
    - **原因**: GTX 1060 (Pascal 架构, Compute Capability 6.1) 不被最新版 PyTorch (默认 CUDA 12.x, Compute Capability 7.0+) 支持。
    - **效果**: 修复 `UserWarning: NVIDIA GeForce GTX 1060 6GB ... is not compatible` 错误，确保 GPU 可用。

### 1.3 构建脚本更新
- **文件**: `Daisy_server/scripts/build_local_image.ps1`
- **变更**: 设置环境变量 `$env:DOCKER_BUILDKIT = 1` 以启用高级构建特性。

## 2. 验证与执行

### 2.1 必须的操作
由于 `Dockerfile.base` 已更新，**必须删除旧的基础镜像**以强制重新构建：

```powershell
docker rmi daisy_server:base
```

然后运行构建脚本：

```powershell
cd e:\Daisy\Daisy_Demo\Daisy_server\scripts
.\build_local_image.ps1
```

### 2.2 异常说明
在尝试自动执行上述命令时，检测到 **Docker Desktop 可能未响应** (`error during connect ... open //./pipe/dockerDesktopLinuxEngine`).

**请检查 Docker Desktop 是否正在运行**，然后手动执行上述命令。
