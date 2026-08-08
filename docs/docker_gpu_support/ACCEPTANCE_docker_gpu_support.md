# ACCEPTANCE_docker_gpu_support

## 1. 变更摘要
- **修改文件**: `e:\Daisy\Daisy_Demo\Daisy_server\scripts\build_local_image.ps1`
- **变更内容**: 在 `docker run` 命令中添加了 `--gpus all` 参数。

## 2. 验证步骤
请按以下步骤验证 GPU 是否成功挂载：

1. **重新构建并启动容器**:
   在 PowerShell 中运行:
   ```powershell
   cd e:\Daisy\Daisy_Demo\Daisy_server\scripts
   .\build_local_image.ps1
   ```

2. **验证 GPU 可见性**:
   容器启动后，运行以下命令：
   ```powershell
   docker exec -it daisy_server_local_container python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'Device count: {torch.cuda.device_count()}'); print(f'Device name: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None'}')"
   ```

3. **预期输出**:
   ```
   CUDA available: True
   Device count: 1 (或更多)
   Device name: NVIDIA GeForce RTX ...
   ```

## 3. 故障排除
- 如果报错 `docker: Error response from daemon: could not select device driver ""`，请确保已安装 NVIDIA 驱动，并且 Docker Desktop 的 WSL 2 Backend 已启用。
