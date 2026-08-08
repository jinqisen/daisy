# TASK_local_model_packaging_persistence

## 任务列表

### Task 1: 修改 build_local_image.ps1
- **文件**: `e:\Daisy\Daisy_Demo\Daisy_server\scripts\build_local_image.ps1`
- **步骤**:
  1. 在 `docker run` 之前添加 `sqlite.db` 存在性检查和创建逻辑。
  2. 修改 `docker run` 命令，添加 `-v` 参数。
- **验收**: 检查脚本内容，确认逻辑正确。

## 依赖关系
无外部依赖。
