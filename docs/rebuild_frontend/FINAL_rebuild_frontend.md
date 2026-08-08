# FINAL_rebuild_frontend

## 1. 项目总结
- **任务**: 基于 `.env` 配置重新编译打包前端镜像。
- **结果**: 成功生成 Docker 镜像包。
- **配置**:
    - `VITE_API_BASE_URL`: `http://171.43.173.125:30026/api`
    - `VITE_PORT`: `30020`

## 2. 交付物
- **Docker 镜像包**: `Daisy_front\image\remote\daisyFront_remote_20251224_113929.tar`

## 3. 部署指南 (Remote)
1. 将 `.tar` 文件传输到远程服务器。
2. 加载镜像:
   ```bash
   docker load -i daisyFront_remote_20251224_113929.tar
   ```
3. 运行容器:
   ```bash
   docker run -d --name daisy_front -p 30020:80 --restart unless-stopped daisy_front_remote:20251224_113929
   ```
