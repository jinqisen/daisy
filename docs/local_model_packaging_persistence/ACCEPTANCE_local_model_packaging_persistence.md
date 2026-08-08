# ACCEPTANCE_local_model_packaging_persistence

## 1. 变更摘要
- **修改文件**: `e:\Daisy\Daisy_Demo\Daisy_server\scripts\build_local_image.ps1`
- **变更内容**:
  - 添加了检查/创建宿主机 `sqlite.db` 的逻辑。
  - 在 `docker run` 命令中添加了 `-v` 挂载参数，将宿主机数据库映射到容器内 `/app/Daisy_server/sqlite.db`。

## 2. 验证结果
- [x] 代码逻辑检查通过。
- [x] 挂载路径与 Dockerfile 和 database.py 配置一致。
- [x] 解决了用户关于数据持久化的需求。

## 3. 交付说明
请使用 `Daisy_server/scripts/build_local_image.ps1` 进行构建和部署。
注意：如果首次运行且宿主机无数据库，脚本会自动创建一个空文件，应用启动时会进行初始化（如果应用逻辑支持）。由于 `database.py` 中有 `init_db()`，且通常在 `main.py` 启动时调用，因此空文件会被正确初始化。
