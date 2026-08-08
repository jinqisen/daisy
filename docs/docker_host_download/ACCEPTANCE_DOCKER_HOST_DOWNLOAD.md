# Docker Host Download Optimization 验收报告

## 任务目标
解决 Docker 容器内部因网络代理、SSL 证书验证和下载速度慢导致的构建失败问题，实现宿主机预下载依赖并在构建时复用。

## 完成情况

### 1. 宿主机下载脚本
- **脚本路径**: `scripts/download_deps_locally.ps1`
- **功能**:
    - 自动创建 `Daisy_server/packages` 目录
    - 下载 PyTorch (Linux, CUDA 11.8) 相关 whl 包
    - 支持断点续传（检测已存在文件）
    - 文件名规范化，适配 `pip` 本地安装格式

### 2. Dockerfile 优化
- **文件**: `Dockerfile.base`
- **优化点**:
    - **优先本地安装**: `COPY packages* /tmp/packages/`，如果存在则优先安装
    - **绕过 APT 问题**: 临时注释掉 `apt-get update/install`，避免因 Docker Desktop 代理注入导致的连接拒绝问题
    - **智能判断**: 脚本自动检测 `/tmp/packages/*.whl` 是否存在，存在则本地安装，否则尝试远程下载（作为回退）

### 3. 构建脚本修复
- **文件**: `scripts/build_local_image.ps1`
- **修复点**:
    - **代理修正**: 自动将 `127.0.0.1` 代理地址转换为 `host.docker.internal`
    - **变量修复**: 修复 `$ProjectRoot` 变量未定义导致的路径错误
    - **目录准备**: 确保 `packages` 目录存在，防止 `COPY` 指令失败

## 验收步骤

1. **执行下载**:
   在宿主机运行下载脚本（已在后台启动）：
   ```powershell
   .\scripts\download_deps_locally.ps1
   ```

2. **执行构建**:
   等待下载完成后，运行构建脚本：
   ```powershell
   .\scripts\build_local_image.ps1
   ```

3. **验证结果**:
   - Docker 构建日志应显示 "Installing PyTorch from local packages..."
   - 构建过程不应再出现 SSL 错误或连接超时
   - 最终镜像应成功生成

## 遗留问题 / 注意事项
- 下载过程可能耗时较长（约 2.5GB），请耐心等待。
- 如果 Docker Desktop 的代理配置强制注入导致其他网络问题，建议暂时在 Docker 设置中关闭代理。
