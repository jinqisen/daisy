我将分五个阶段系统修复上述质量问题，优先解决阻碍运行的编译错误和高危安全隐患，最后完善测试与异常处理。

### 1. 清理仓库与编译修复 (P0)
- **目标**: 解决 `compileall` 失败问题，确保代码可被工具链正常处理。
- **动作**:
  - 递归删除仓库内所有干扰性的 macOS AppleDouble 文件 (`._*`)。
  - 重新运行 `python -m compileall app` 验证修复。

### 2. 安全加固 (P0)
- **目标**: 移除代码库中的明文密钥，修复 CORS 宽泛配置。
- **动作**:
  - **密钥迁移**:
    - 检查 `.env` 文件，将 `server_config.json` 中的敏感密钥 (`MAAS_API_KEY`, `HUAWEI_SEARCH_API_KEY`, `SECRET_KEY`) 迁移至 `.env`。
    - 将 `server_config.json` 中的密钥值替换为 `null` 或占位符，使其不再硬编码。
  - **CORS 修复**:
    - 修改 `app/core/config.py`，将默认 `ALLOWED_ORIGINS` 从 `["*"]` 改为安全的本地开发白名单 (如 `http://localhost:3000`, `http://127.0.0.1:8000`)。
    - 检查 `app/main.py` 确保中间件配置引用了正确的设置。

### 3. 依赖与测试基建修复 (P2)
- **目标**: 统一依赖声明，确保测试可运行。
- **动作**:
  - 将 `pytest` 及相关测试依赖添加到 `requirements.txt`。
  - 尝试安装缺失依赖 (需用户确认环境)。
  - 运行 `pytest -q` 验证测试框架是否正常启动。

### 4. 异常处理与稳定性改进 (P1)
- **目标**: 防止内部错误信息泄露给前端，修复日志丢失堆栈问题。
- **动作**:
  - 修改 `app/api/routers/chat.py` 的异常捕获逻辑，对未预期的 500 错误仅返回通用提示（如 "Internal Server Error"），同时在服务端记录完整堆栈。
  - 修复 `app/core/logger.py` 中的 `monitor_execution_time` 装饰器，将 `raise e` 改为 `raise` 以保留原始异常堆栈信息。

### 5. 最终验证
- **动作**:
  - 执行全量编译检查。
  - 运行基础测试。
  - 检查配置加载逻辑是否正常（确保迁移密钥后应用仍能启动）。
