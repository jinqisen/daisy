# ALIGNMENT_local_model_packaging_persistence

## 1. 项目上下文分析

### 现有项目结构
- **Daisy_front**: 前端 React 项目，包含 Dockerfile (Python static server) 和构建脚本。
- **Daisy_server**: 后端 Python/FastAPI 项目，包含 `sqlite.db`，Dockerfile 和构建脚本。
- **关键文件**:
  - `Daisy_server/sqlite.db`: SQLite 数据库文件。
  - `Daisy_server/scripts/build_local_image.ps1`: 后端构建和部署脚本。
  - `Daisy_front/scripts/build_local_image.ps1`: 前端构建和部署脚本。

### 需求理解
- **原始需求**: "本地模型打包更新我需要你做一下调整，保留sqlite.db，不要每次部署安装都初始化了。"
- **目标**: 在本地 Docker 部署中持久化 SQLite 数据库，防止重启/重新部署时数据丢失。
- **路径差异**: 用户提供的路径是 `Daisy_front/scripts/build_local_image.ps1`，但实际上 `sqlite.db` 位于 `Daisy_server` 且由后端使用。前端项目虽然有 Dockerfile (Python base)，但仅用于静态服务，不涉及 SQLite。

## 2. 疑问与决策

### 关键决策点
- **歧义**: 用户指向前端脚本，但需求描述符合后端行为。
- **决策**: 
  - 判定用户意图为修改 **Daisy_server** 的构建脚本，因为 `sqlite.db` 属于后端。
  - 如果用户实际上是在前端镜像中集成了后端（虽然当前文件结构不支持此假设），则需要进一步澄清。
  - **策略**: 默认修改 `Daisy_server/scripts/build_local_image.ps1`，并添加挂载逻辑。

## 3. 规范定义

### 变更范围
- **目标文件**: `e:\Daisy\Daisy_Demo\Daisy_server\scripts\build_local_image.ps1`
- **变更内容**: 
  - 在 `docker run` 命令中添加 Volume 挂载。
  - 映射宿主机 `Daisy_server/sqlite.db` 到容器内 `/app/sqlite.db` (根据 `DB_PATH` 逻辑)。

### 技术实现
- 宿主机路径: `$ServerDir/sqlite.db`
- 容器路径: `/app/sqlite.db` (基于 `WORKDIR /app` 和 `database.py` 中 `DB_PATH` 的相对位置)
  - `database.py`: `DB_PATH = .../Daisy_server/sqlite.db`
  - Dockerfile `WORKDIR /app` -> `COPY . /app/Daisy_server` (Wait, let's check Dockerfile structure again)

### 验证标准
- 脚本执行无误。
- `docker run` 命令包含 `-v ...:...+` 参数。
- 能够正常启动容器。
