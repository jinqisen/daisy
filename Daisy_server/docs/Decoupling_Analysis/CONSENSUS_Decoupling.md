# CONSENSUS_Decoupling

## 1. 目标
解除 `Daisy_server` 对 `Daisy_prompts` 的硬编码物理路径依赖，转为**配置驱动**的依赖方式。

## 2. 技术方案

### 2.1 环境变量优先
- 引入环境变量 `DAISY_PROMPTS_DIR`。
- **优先级 1**: 环境变量 `DAISY_PROMPTS_DIR` (如果设置)。
- **优先级 2**: 默认容器路径 `/app/Daisy_prompts` (标准 Docker 部署路径)。
- **优先级 3 (Fallback)**: `../../../Daisy_prompts` (保留用于向后兼容本地开发，但记录警告日志)。

### 2.2 配置文件更新
- 在本地开发环境 (`.env`) 中，显式设置 `DAISY_PROMPTS_DIR` 指向本地的 `Daisy_prompts` 目录。
- 这样 Server 就不需要“猜测”路径，而是明确知道路径。

### 2.3 代码重构
- 修改 `app/core/prompt_loader.py` 的 `_find_prompts_dir` 方法。

## 3. 验收标准
1.  在 `.env` 中配置错误路径时，Server 应报错或回退（并记录日志）。
2.  在 `.env` 中配置正确路径时，Server 正常启动。
3.  不配置 `.env` 但保持原有目录结构时，Server 仍能启动（Fallback生效），但有 Warning。
