# ACCEPTANCE_Build_Scripts_Strict

## 1. 变更确认
根据用户要求，构建脚本已调整为**严格模式**，移除了所有路径回退逻辑。

### 1.1 `build_local_image.ps1`
- **源文件**: 强制要求 `.local_env` 存在。
- **变量**: 强制要求 `.local_env` 中定义 `DAISY_PROMPTS_DIR`。
- **验证**: 目录不存在则抛出异常，**不会**回退到兄弟目录。

### 1.2 `build_remote_image.ps1`
- **源文件**: 强制要求 `.env` 存在。
- **变量**: 强制要求 `.env` 中定义 `DAISY_PROMPTS_DIR`。
- **验证**: 目录不存在则抛出异常，**不会**回退到兄弟目录。

## 2. 验证步骤建议
1. 确保 `Daisy_server/.local_env` 存在且包含 `DAISY_PROMPTS_DIR=...`。
2. 确保 `Daisy_server/.env` 存在且包含 `DAISY_PROMPTS_DIR=...`。
3. 运行构建脚本，观察输出。

## 3. 结论
脚本现在完全符合“无回退、显式报错、环境隔离”的要求。
