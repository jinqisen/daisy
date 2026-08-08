# CONSENSUS_local_model_packaging_persistence

## 1. 最终共识

### 需求描述
用户希望在本地 Docker 部署 `Daisy_server` 时，保留 `sqlite.db` 数据库文件，避免每次重新部署时数据被重置。虽然用户提及的路径是前端脚本，但根据项目结构，确认实际需要修改的是后端服务器脚本。

### 验收标准
1. **持久化**: `sqlite.db` 必须挂载到宿主机，确保容器重启或删除后数据不丢失。
2. **自动化**: `build_local_image.ps1` 脚本自动处理挂载参数。
3. **兼容性**: 不影响现有的环境变量注入和端口映射。

## 2. 技术方案

### 修改文件
`e:\Daisy\Daisy_Demo\Daisy_server\scripts\build_local_image.ps1`

### 实现细节
1. **检查/创建 DB 文件**: 在运行容器前，检查宿主机 `$ServerDir/sqlite.db` 是否存在。如果不挂载文件而挂载目录，可能会导致问题（如果 DB 是文件）。为了安全，如果宿主机没有 DB 文件，Docker 可能会把它当成目录挂载，或者报错。
   - **策略**: 如果宿主机 `sqlite.db` 不存在，先创建一个空文件？
   - 不，SQLite 引擎会自动创建文件。但是如果作为 Volume 挂载，如果宿主机文件不存在，Docker (在某些版本/配置下) 会创建一个**目录**。
   - **最佳实践**: 脚本中显式检查 `Test-Path $ServerDir/sqlite.db`。如果不存，则 `New-Item -ItemType File` 创建一个空文件，或者让 Python 应用首次运行时创建（但这需要先不挂载？不行）。
   - 实际上，如果宿主机文件不存在，Docker 挂载时会创建一个目录。这会导致 SQLite 报错 "disk I/O error" 或 "is a directory"。
   - **解决方案**: 在脚本中，在 `docker run` 之前，检查 `sqlite.db` 是否存在。如果不存在，创建一个空文件。

2. **Docker Run 参数**:
   添加 `-v "${ServerDir}/sqlite.db:/app/Daisy_server/sqlite.db"`

### 风险控制
- 确保容器内的路径 `/app/Daisy_server/sqlite.db` 正确无误。

## 3. 任务计划
- [x] 确认路径和挂载点。
- [ ] 修改 `Daisy_server/scripts/build_local_image.ps1`。
- [ ] 验证脚本逻辑。
