# TASK_docker_gpu_support

## 任务列表

### Task 1: 修改构建脚本
- **文件**: `e:\Daisy\Daisy_Demo\Daisy_server\scripts\build_local_image.ps1`
- **操作**: 在 `docker run` 命令中插入 `--gpus all`。
- **验收**: 脚本语法正确，参数位置正确。

### Task 2: 验证指南
- **操作**: 提供验证命令给用户。
- **验收**: 用户确认 GPU 可用。
