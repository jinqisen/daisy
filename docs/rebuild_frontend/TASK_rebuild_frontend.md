# TASK_rebuild_frontend

## 任务列表

### 1. 执行构建脚本
- **输入**: `scripts/build_remote_image.ps1`
- **操作**: 在 PowerShell 中运行脚本。
- **验收标准**: 脚本运行无报错，提示 "Export successful"。

### 2. 验证构建产物
- **输入**: `image/remote` 目录
- **操作**: 检查是否存在新的 `.tar` 文件。
- **验收标准**: 文件存在且时间戳为最新。
