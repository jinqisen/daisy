# ACCEPTANCE_Build_Scripts

## 1. 验证结果
- [x] **`build_local_image.ps1` 修订**:
    - 脚本现在会解析 `.local_env` (优先) 或 `.env` 文件，查找 `DAISY_PROMPTS_DIR` 变量。
    - 如果配置存在，则使用配置路径；否则回退到原有的兄弟目录逻辑。
    - 启动容器时，显式注入 `-e DAISY_PROMPTS_DIR=/app/Daisy_prompts`，确保容器内部的 `PromptLoader` 使用正确路径（无论容器外的路径在哪里，挂载点始终是 `/app/Daisy_prompts`）。

- [x] **`build_remote_image.ps1` 修订**:
    - 脚本现在会解析 `.env` 文件查找 `DAISY_PROMPTS_DIR`。
    - 同样支持配置优先，回退兼容的逻辑。
    - 复制逻辑 (`Copy-Item`) 将使用解析出的源路径。

## 2. 结论
构建脚本已更新，完全支持解耦后的配置驱动模式。现在可以通过 `.env` 灵活指定 Prompts 目录，脚本能正确识别并执行构建和挂载。
