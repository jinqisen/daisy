# DESIGN_local_model_packaging_persistence

## 1. 架构设计

### 部署架构变更
- **Before**: 容器内 `sqlite.db` (Ephemeral)
- **After**: 宿主机 `sqlite.db` <--> 容器内 `sqlite.db` (Persistent Volume Mount)

### 数据流
1. `build_local_image.ps1` 启动。
2. 检查宿主机 `Daisy_server/sqlite.db`。如果不存，创建空文件。
3. `docker run` 启动容器，挂载该文件。
4. `Daisy_server` 应用启动，SQLAlchemy 连接 `/app/Daisy_server/sqlite.db`。
5. 数据写入宿主机文件。

## 2. 接口与配置
无接口变更。
配置变更仅限于 Docker 运行时参数。
